import re
from urllib.parse import urlparse

from services.utils import escape_html


VERDICT_FAMILY_EMOJIS = {
    "true": "✅",
    "mixed": "⚠️",
    "false": "❌",
    "uncertain": "🔎",
    "other": "ℹ️",
}

LEGACY_VERDICT_FAMILIES = {
    "правда": "true",
    "переважно правда": "mixed",
    "правда з уточненням": "mixed",
    "потребує контексту": "mixed",
    "частково неправда": "false",
    "маніпуляція": "mixed",
    "оманливе твердження": "mixed",
    "застарілий контекст": "mixed",
    "стара новина": "mixed",
    "фейк": "false",
    "неправда": "false",
    "підробка": "false",
    "хибна цитата": "false",
    "непідтверджено": "uncertain",
    "недостатньо даних": "uncertain",
    "інше": "other",
    "реклама": "other",
    "думка": "other",
    "сатира": "other",
    "не підлягає перевірці": "other",
}

# Compatibility for modules and old saved entries that still import this mapping.
VERDICT_EMOJIS = {
    label.title(): VERDICT_FAMILY_EMOJIS[family]
    for label, family in LEGACY_VERDICT_FAMILIES.items()
}
VERDICT_EMOJIS.update({
    "Правда": "✅",
    "Фейк": "❌",
    "Маніпуляція": "⚠️",
    "Недостатньо даних": "🔎",
    "Правда з уточненням": "⚠️",
    "Частково неправда": "❌",
    "Непідтверджено": "🔎",
    "Реклама": "ℹ️",
    "Інше": "ℹ️",
})

MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
RAW_URL_RE = re.compile(r"\(?https?://[^\s)]+\)?")
TRAILING_DOMAIN_CITATION_RE = re.compile(
    r"\s*(?:\(|\[)?(?:https?://)?(?:www\.)?[A-Za-z0-9-]+"
    r"(?:\.[A-Za-z0-9-]+)+(?:/[^\s)\]]*)?(?:\)|\])?[.,;:]?\s*$",
    re.IGNORECASE,
)


def normalize_verdict_label(verdict: str | None) -> str:
    label = clean_model_text(str(verdict or "").strip())
    label = re.sub(r"\s+", " ", label).strip(" —:-")

    if not label:
        return "Недостатньо даних"

    if len(label) > 45:
        return "Недостатньо даних"

    return label


def get_verdict_family(result_or_verdict: dict | str | None) -> str:
    if isinstance(result_or_verdict, dict):
        family = str(result_or_verdict.get("verdict_family", "")).strip().lower()
        verdict = normalize_verdict_label(result_or_verdict.get("verdict"))

        if family in VERDICT_FAMILY_EMOJIS:
            return family
    else:
        verdict = normalize_verdict_label(result_or_verdict)

    lowered = verdict.casefold()

    if lowered in LEGACY_VERDICT_FAMILIES:
        return LEGACY_VERDICT_FAMILIES[lowered]

    if any(word in lowered for word in ("фейк", "неправд", "підроб", "вигад", "хибн")):
        return "false"

    if any(word in lowered for word in ("маніп", "оман", "контекст", "перебільш", "застар")):
        return "mixed"

    if any(word in lowered for word in ("непідтверд", "недостат", "невідом", "не встанов")):
        return "uncertain"

    if "правд" in lowered or "підтвердж" in lowered:
        return "true"

    return "other"


def get_verdict_emoji(result_or_verdict: dict | str | None) -> str:
    return VERDICT_FAMILY_EMOJIS[get_verdict_family(result_or_verdict)]


def format_verdict_line(result: dict, include_reason: bool = True) -> str:
    verdict = normalize_verdict_label(result.get("verdict"))
    reason = clean_model_text(result.get("short_reason", "").strip())
    emoji = get_verdict_emoji(result)
    line = f"{emoji} <b>{escape_html(verdict)}</b>"

    if include_reason and reason and get_verdict_family(result) != "true":
        line += f" — {escape_html(reason)}"

    return line


def format_fact_check_response(result: dict) -> str:
    summary = clean_model_text(result.get("summary", "").strip())
    blocks = result.get("blocks", [])
    sources = result.get("sources", [])
    parts = [format_verdict_line(result)]

    if summary:
        parts.extend(["", escape_html(summary)])

    added_block_texts = set()

    for block in blocks[:1]:
        block_text = clean_model_text(block.get("text", "").strip())

        if not block_text or is_duplicate_block(block_text, summary, added_block_texts):
            continue

        if str(block.get("type", "")).strip() == "Уточнення":
            display_text = re.sub(r"^Уточнення\s*:\s*", "", block_text, flags=re.IGNORECASE).strip()
            if not display_text:
                continue
            parts.extend(["", f"<b>Уточнення:</b> {escape_html(display_text)}"])
        else:
            parts.extend(["", escape_html(block_text)])

        added_block_texts.add(normalize_for_compare(block_text))

    formatted_sources = format_sources(sources)

    if formatted_sources:
        parts.extend(["", "<b>Джерела перевірки:</b>"])
        parts.extend(formatted_sources)

    return "\n".join(parts).strip()


def clean_model_text(text: str, strip_trailing_citation: bool = True) -> str:
    if not text:
        return ""

    text = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), text)
    text = RAW_URL_RE.sub("", text)
    # The model can occasionally leave a source marker such as "(who.int"
    # in narrative text. Sources are rendered separately below the answer.
    if strip_trailing_citation:
        previous = None
        while previous != text:
            previous = text
            text = TRAILING_DOMAIN_CITATION_RE.sub("", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip(" \n\t()[]")


def is_duplicate_block(block_text: str, summary: str, added_block_texts: set[str]) -> bool:
    normalized = normalize_for_compare(block_text)

    if not normalized or normalized in added_block_texts:
        return True

    summary_normalized = normalize_for_compare(summary)

    if normalized in summary_normalized or summary_normalized in normalized:
        return True

    return False


def normalize_for_compare(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def format_sources(sources: list[dict], limit: int = 5) -> list[str]:
    formatted = []
    seen_urls = set()

    for source in sources[:limit]:
        title = clean_model_text(
            str(source.get("title", "")).strip(),
            strip_trailing_citation=False,
        )
        url = str(source.get("url", "")).strip()

        if not title or not is_valid_url(url) or url in seen_urls:
            continue

        safe_title = escape_html(get_source_name(title, url))
        safe_url = escape_html(url)
        formatted.append(f'• <a href="{safe_url}">{safe_title}</a>')
        seen_urls.add(url)

    return formatted


def get_source_name(title: str, url: str) -> str:
    if len(title) <= 70:
        return title

    return title[:67].rstrip() + "..."


def get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.removeprefix("www.")
    except ValueError:
        return ""


def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def extract_verdict_from_result(result: dict) -> str:
    return normalize_verdict_label(result.get("verdict"))
