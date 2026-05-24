"""Lightweight local analysis helpers for AntiFakeUA_Bot.

This module does not call GPT and does not spend tokens. It is meant to run
before the expensive AI check and add useful signals to the final report:
- stale/old-news risk;
- emotional manipulation markers;
- URLs/domains extraction;
- simple claim extraction;
- suggested check depth and credit cost.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

from services.utils import escape_html


URL_RE = re.compile(r"https?://[^\s)\]>\"']+", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(20[0-2][0-9])\b")
DATE_RE = re.compile(
    r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](20[0-2][0-9])\b"
)

EMOTIONAL_MARKERS = {
    "терміново": "нагнітання терміновості",
    "шок": "емоційний клікбейт",
    "жах": "емоційний тиск",
    "катастрофа": "катастрофізація",
    "всі мовчать": "натяк на змову/замовчування",
    "ніхто не говорить": "натяк на змову/замовчування",
    "поширте": "заклик до вірусного поширення",
    "репост": "заклик до вірусного поширення",
    "нас зливають": "емоційно-політичне нагнітання",
    "зрада": "оцінне політичне маркування",
    "перемога": "оцінне політичне маркування",
    "без паніки": "потенційне нагнітання паніки",
}

STALE_MARKERS = {
    "сьогодні": "подається як актуальна подія",
    "щойно": "подається як нова подія",
    "прямо зараз": "подається як нова подія",
    "терміново": "подається як термінова подія",
    "вперше": "заявлена новизна потребує перевірки",
}

FACT_VERBS = (
    "заявив", "заявила", "повідомив", "повідомила", "ухвалив", "ухвалила",
    "підписав", "підписала", "заборонив", "заборонила", "дозволив",
    "дозволила", "почав", "почала", "ввів", "ввела", "скасував",
    "скасувала", "затримали", "обстріляли", "прийняли", "планують",
)


@dataclass(slots=True)
class LightweightAnalysis:
    urls: list[str]
    domains: list[str]
    extracted_claim: str
    emotional_markers: list[str]
    stale_news_risk: bool
    stale_reasons: list[str]
    detected_years: list[int]
    detected_dates: list[str]
    suggested_mode: str
    suggested_credits: int

    def to_dict(self) -> dict:
        return asdict(self)


def extract_urls(text: str) -> list[str]:
    return URL_RE.findall(text or "")


def extract_domains(urls: Iterable[str]) -> list[str]:
    domains: list[str] = []
    for url in urls:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().removeprefix("www.")

        if domain in {"t.me", "telegram.me"}:
            channel = parsed.path.strip("/").split("/", 1)[0].lower()

            if channel:
                domain = f"{domain}/{channel}"

        if domain and domain not in domains:
            domains.append(domain)
    return domains


def extract_dates(text: str) -> tuple[list[int], list[str]]:
    years = sorted({int(match.group(1)) for match in YEAR_RE.finditer(text or "")})
    dates = []
    for match in DATE_RE.finditer(text or ""):
        day, month, year = match.groups()
        dates.append(f"{int(day):02d}.{int(month):02d}.{year}")
    return years, dates


def detect_emotional_markers(text: str) -> list[str]:
    lowered = (text or "").lower()
    found = []
    for marker, description in EMOTIONAL_MARKERS.items():
        if marker in lowered and description not in found:
            found.append(description)
    if "!!!" in text:
        found.append("надмірне використання знаків оклику")
    if sum(1 for ch in text if ch.isupper()) > max(20, len(text) * 0.25):
        found.append("надмірне використання великих літер")
    return found


def detect_stale_news_risk(text: str, now: datetime | None = None) -> tuple[bool, list[str]]:
    now = now or datetime.now(timezone.utc)
    lowered = (text or "").lower()
    reasons = []

    for marker, reason in STALE_MARKERS.items():
        if marker in lowered and reason not in reasons:
            reasons.append(reason)

    years, dates = extract_dates(text)
    old_years = [year for year in years if year < now.year]
    if old_years and reasons:
        reasons.append(f"у тексті є старі роки: {', '.join(map(str, old_years))}")
    if dates and reasons:
        reasons.append("у тексті є конкретні дати, які треба звірити з першоджерелами")

    return bool(old_years and reasons), reasons


def extract_main_claim(text: str, max_len: int = 300) -> str:
    clean = " ".join((text or "").split())
    if not clean:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", clean)
    for sentence in sentences:
        lowered = sentence.lower()
        if any(verb in lowered for verb in FACT_VERBS):
            return sentence[:max_len].strip()

    return clean[:max_len].strip()


def suggest_mode(text: str, has_image: bool = False) -> tuple[str, int]:
    length = len(text or "")
    urls = extract_urls(text)
    emotional = detect_emotional_markers(text)
    stale_risk, _ = detect_stale_news_risk(text)

    credits = 1
    mode = "quick"

    if length > 1200:
        credits += 1
    if urls:
        credits += 1
        mode = "source_check"
    if emotional or stale_risk:
        credits += 1
        mode = "enhanced"
    if has_image:
        credits += 2
        mode = "image_or_ocr"

    return mode, min(credits, 5)


def analyze_lightweight(text: str, has_image: bool = False) -> LightweightAnalysis:
    urls = extract_urls(text)
    domains = extract_domains(urls)
    years, dates = extract_dates(text)
    stale_risk, stale_reasons = detect_stale_news_risk(text)
    mode, credits = suggest_mode(text, has_image=has_image)

    return LightweightAnalysis(
        urls=urls,
        domains=domains,
        extracted_claim=extract_main_claim(text),
        emotional_markers=detect_emotional_markers(text),
        stale_news_risk=stale_risk,
        stale_reasons=stale_reasons,
        detected_years=years,
        detected_dates=dates,
        suggested_mode=mode,
        suggested_credits=credits,
    )


def format_lightweight_block(analysis: LightweightAnalysis, content_history: dict | None = None) -> str:
    lines = ["", "📌 <b>Локальний інфоаналіз:</b>"]

    if analysis.extracted_claim:
        lines.append(f"• Основне твердження: {escape_html(analysis.extracted_claim)}")

    if analysis.domains:
        domains = ", ".join(escape_html(domain) for domain in analysis.domains)
        lines.append(f"• Виявлені домени: {domains}")

    if content_history and content_history.get("is_repeat"):
        lines.append(
            "• 🔁 Такий самий текст уже траплявся в базі: "
            f"{content_history.get('times_seen')} раз(и)"
        )
        first_seen_at = content_history.get("first_seen_at")

        if first_seen_at:
            lines.append(f"• Перша фіксація: {escape_html(first_seen_at)}")

    if analysis.stale_news_risk:
        lines.append("• ⚠️ Є ризик, що стару інформацію подано як нову")

    if analysis.stale_reasons:
        reasons = "; ".join(escape_html(reason) for reason in analysis.stale_reasons[:4])
        lines.append(f"• Ознаки застарілості: {reasons}")

    if analysis.emotional_markers:
        markers = "; ".join(escape_html(marker) for marker in analysis.emotional_markers[:5])
        lines.append(f"• Ознаки маніпулятивної подачі: {markers}")

    if analysis.detected_dates:
        dates = ", ".join(escape_html(date) for date in analysis.detected_dates)
        lines.append(f"• Дати в тексті: {dates}")

    if analysis.detected_years:
        years = ", ".join(map(str, analysis.detected_years))
        lines.append(f"• Роки в тексті: {years}")

    lines.append(f"• Рекомендований режим: {escape_html(analysis.suggested_mode)}")
    lines.append(f"• Орієнтовна вага перевірки: {analysis.suggested_credits} кредит(и)")

    return "\n".join(lines).strip()
