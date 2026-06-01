"""Helpers for recording the history of sources used in fact-checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


FAMILY_FIELD_MAP = {
    "true": "true_count",
    "mixed": "manipulation_count",
    "false": "fake_count",
    "uncertain": "unverified_count",
    "other": "unverified_count",
}


VERDICT_FIELD_MAP = {
    "правда": "true_count",
    "переважно правда": "manipulation_count",
    "потребує контексту": "manipulation_count",
    "маніпуляція": "manipulation_count",
    "оманливе твердження": "manipulation_count",
    "застарілий контекст": "stale_count",
    "фейк": "fake_count",
    "неправда": "fake_count",
    "підробка": "fake_count",
    "хибна цитата": "fake_count",
    "непідтверджено": "unverified_count",
    "непідтверджено": "unverified_count",
    "недостатньо даних": "unverified_count",
    "інше": "unverified_count",
    "старий контент": "stale_count",
    "стара новина": "stale_count",
}


@dataclass(slots=True)
class SourceRecord:
    id: int
    name: str
    source_type: str
    url: str | None
    domain: str | None
    reliability_score: float


def normalize_domain(url: str | None) -> str | None:
    if not url:
        return None

    parsed = urlparse(
        url if url.startswith(("http://", "https://")) else f"https://{url}"
    )
    domain = parsed.netloc.lower().removeprefix("www.")

    if domain in {"t.me", "telegram.me"}:
        channel = parsed.path.strip("/").split("/", 1)[0].lower()

        if channel:
            return f"{domain}/{channel}"

    return domain or None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_or_create_source(
    conn: Any,
    *,
    name: str,
    source_type: str = "website",
    url: str | None = None,
) -> int:
    domain = normalize_domain(url)

    if domain:
        existing = conn.execute(
            """
            SELECT id FROM sources
            WHERE lower(name) = lower(%s) OR domain = %s
            LIMIT 1
            """,
            (name, domain),
        ).fetchone()
    else:
        existing = conn.execute(
            """
            SELECT id FROM sources
            WHERE lower(name) = lower(%s)
            LIMIT 1
            """,
            (name,),
        ).fetchone()

    if existing:
        return int(existing["id"])

    created = conn.execute(
        """
        INSERT INTO sources (name, type, url, domain, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (name, source_type, url, domain, utc_now(), utc_now()),
    ).fetchone()

    return int(created["id"])


def update_source_verdict(
    conn: Any,
    *,
    source_id: int,
    verdict: str,
    verdict_family: str | None = None,
) -> None:
    field = FAMILY_FIELD_MAP.get(
        (verdict_family or "").strip().lower(),
        VERDICT_FIELD_MAP.get(verdict.strip().lower(), "unverified_count"),
    )
    conn.execute(
        f"""
        UPDATE sources
        SET {field} = COALESCE({field}, 0) + 1,
            updated_at = %s
        WHERE id = %s
        """,
        (utc_now(), source_id),
    )
    recalculate_reliability(conn, source_id=source_id)


def recalculate_reliability(conn: Any, *, source_id: int) -> None:
    row = conn.execute(
        """
        SELECT true_count, fake_count, manipulation_count, unverified_count, stale_count
        FROM sources
        WHERE id = %s
        """,
        (source_id,),
    ).fetchone()

    if not row:
        return

    true_count = row["true_count"] or 0
    fake_count = row["fake_count"] or 0
    manipulation_count = row["manipulation_count"] or 0
    unverified_count = row["unverified_count"] or 0
    stale_count = row["stale_count"] or 0
    total = true_count + fake_count + manipulation_count + unverified_count + stale_count

    if total == 0:
        score = 50.0
    else:
        positive = true_count * 1.0
        negative = (
            fake_count * 1.0
            + manipulation_count * 0.6
            + stale_count * 0.4
            + unverified_count * 0.15
        )
        score = max(0.0, min(100.0, 50.0 + ((positive - negative) / total) * 50.0))

    conn.execute(
        "UPDATE sources SET reliability_score = %s, updated_at = %s WHERE id = %s",
        (round(score, 2), utc_now(), source_id),
    )


def record_source_mention(
    conn: Any,
    *,
    source_id: int,
    check_id: int | None,
    url: str | None,
    title: str | None,
    stance: str = "unclear",
    verdict: str = "непідтверджено",
) -> None:
    conn.execute(
        """
        INSERT INTO source_mentions
            (source_id, check_id, url, title, stance, verdict, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (source_id, check_id, url, title, stance, verdict, utc_now()),
    )
