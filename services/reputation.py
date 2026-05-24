"""Source reputation helpers for AntiFakeUA_Bot.

The functions are intentionally simple and SQLite-friendly. They can be used
from handlers after a check is completed to update source statistics.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse


VERDICT_FIELD_MAP = {
    "правда": "true_count",
    "фейк": "fake_count",
    "маніпуляція": "manipulation_count",
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

    parsed = urlparse(url if url.startswith(("http://", "https://")) else f"https://{url}")
    domain = parsed.netloc.lower().removeprefix("www.")

    if domain in {"t.me", "telegram.me"}:
        channel = parsed.path.strip("/").split("/", 1)[0].lower()

        if channel:
            return f"{domain}/{channel}"

    return domain or None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_or_create_source(
    conn: sqlite3.Connection,
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
            WHERE lower(name) = lower(?) OR domain = ?
            LIMIT 1
            """,
            (name, domain),
        ).fetchone()
    else:
        existing = conn.execute(
            """
            SELECT id FROM sources
            WHERE lower(name) = lower(?)
            LIMIT 1
            """,
            (name,),
        ).fetchone()
    if existing:
        return int(existing[0])

    cursor = conn.execute(
        """
        INSERT INTO sources (name, type, url, domain, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name, source_type, url, domain, utc_now(), utc_now()),
    )
    return int(cursor.lastrowid)


def update_source_verdict(
    conn: sqlite3.Connection,
    *,
    source_id: int,
    verdict: str,
) -> None:
    field = VERDICT_FIELD_MAP.get(verdict.strip().lower(), "unverified_count")
    conn.execute(
        f"""
        UPDATE sources
        SET {field} = COALESCE({field}, 0) + 1,
            updated_at = ?
        WHERE id = ?
        """,
        (utc_now(), source_id),
    )
    recalculate_reliability(conn, source_id=source_id)


def recalculate_reliability(conn: sqlite3.Connection, *, source_id: int) -> None:
    row = conn.execute(
        """
        SELECT true_count, fake_count, manipulation_count, unverified_count, stale_count
        FROM sources
        WHERE id = ?
        """,
        (source_id,),
    ).fetchone()
    if not row:
        return

    true_count, fake_count, manipulation_count, unverified_count, stale_count = [value or 0 for value in row]
    total = true_count + fake_count + manipulation_count + unverified_count + stale_count
    if total == 0:
        score = 50.0
    else:
        positive = true_count * 1.0
        negative = fake_count * 1.0 + manipulation_count * 0.6 + stale_count * 0.4 + unverified_count * 0.15
        score = max(0.0, min(100.0, 50.0 + ((positive - negative) / total) * 50.0))

    conn.execute(
        "UPDATE sources SET reliability_score = ?, updated_at = ? WHERE id = ?",
        (round(score, 2), utc_now(), source_id),
    )


def record_source_mention(
    conn: sqlite3.Connection,
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
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (source_id, check_id, url, title, stance, verdict, utc_now()),
    )
