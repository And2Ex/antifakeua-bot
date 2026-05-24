import re
from urllib.parse import urlparse

from services.utils import escape_html


VERDICT_EMOJIS = {
    "Правда": "✅",
    "Фейк": "❌",
    "Маніпуляція": "⚠️",
    "Недостатньо даних": "ℹ️",
    "Інше": "ℹ️",
}

# Додаткові блоки моделі більше не показуються як окремі підзаголовки.
# Вони додаються звичайними абзацами, щоб відповідь виглядала природніше.
BLOCK_EMOJIS = {
    "Деталі": "",
    "Уточнення": "",
    "Застереження": "",
}

LEGACY_BLOCK_TYPES = {
    "Правда",
    "Фейк",
    "Маніпуляція",
    "Недостатньо даних",
}

MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
RAW_URL_RE = re.compile(r"\(?https?://[^\s)]+\)?")


def format_fact_check_response(result: dict) -> str:
    verdict = result.get("verdict", "Недостатньо даних")
    summary = clean_model_text(result.get("summary", "").strip())
    blocks = result.get("blocks", [])
    sources = result.get("sources", [])

    verdict_emoji = VERDICT_EMOJIS.get(verdict, "ℹ️")

    parts = [
        f"{verdict_emoji} <b>{escape_html(verdict)}</b>",
    ]

    if summary:
        parts.extend([
            "",
            escape_html(summary),
        ])

    added_block_texts = set()

    for block in blocks[:3]:
        block_type = normalize_block_type(block.get("type", "Уточнення"), verdict)
        block_text = clean_model_text(block.get("text", "").strip())

        if not block_text:
            continue

        if is_duplicate_block(block_text, summary, added_block_texts):
            continue

        parts.extend([
            "",
            escape_html(block_text),
        ])
        added_block_texts.add(normalize_for_compare(block_text))

    formatted_sources = format_sources(sources)

    if formatted_sources:
        parts.append("")
        parts.append("<b>Джерела:</b>")
        parts.extend(formatted_sources)

    return "\n".join(parts).strip()


def clean_model_text(text: str) -> str:
    if not text:
        return ""

    text = MARKDOWN_LINK_RE.sub(lambda match: match.group(1), text)
    text = RAW_URL_RE.sub("", text)
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip(" \n\t()[]")


def normalize_block_type(block_type: str, verdict: str) -> str:
    if block_type in LEGACY_BLOCK_TYPES:
        if block_type == verdict:
            return "Деталі"
        return "Уточнення"

    if block_type in BLOCK_EMOJIS:
        return block_type

    return "Уточнення"


def is_duplicate_block(block_text: str, summary: str, added_block_texts: set[str]) -> bool:
    normalized = normalize_for_compare(block_text)

    if not normalized:
        return True

    if normalized in added_block_texts:
        return True

    summary_normalized = normalize_for_compare(summary)

    if normalized and summary_normalized and normalized in summary_normalized:
        return True

    return False


def normalize_for_compare(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def format_sources(sources: list[dict], limit: int = 5) -> list[str]:
    formatted_sources = []
    used_urls = set()

    for source in sources[:limit]:
        title = clean_model_text(source.get("title", "").strip())
        url = source.get("url", "").strip()

        if not is_valid_url(url) or url in used_urls:
            continue

        source_name = get_source_name(title, url)

        if source_name:
            formatted_sources.append(
                f'• <a href="{escape_html(url)}">{escape_html(source_name)}</a>'
            )
            used_urls.add(url)

    return formatted_sources


def get_source_name(title: str, url: str) -> str:
    domain = get_domain(url)

    if domain:
        known_names = {
            "reuters.com": "Reuters",
            "apnews.com": "AP News",
            "bbc.com": "BBC",
            "bbc.co.uk": "BBC",
            "kyivindependent.com": "The Kyiv Independent",
            "ukrinform.ua": "Укрінформ",
            "pravda.com.ua": "Українська правда",
            "transparency.org": "Transparency International",
            "worldbank.org": "World Bank",
            "nato.int": "NATO",
            "who.int": "WHO",
            "un.org": "UN",
            "president.gov.ua": "Офіс Президента України",
            "kmu.gov.ua": "Кабінет Міністрів України",
            "rada.gov.ua": "Верховна Рада України",
            "mfa.gov.ua": "МЗС України",
            "mil.gov.ua": "Міноборони України",
        }

        for known_domain, name in known_names.items():
            if domain.endswith(known_domain):
                return name

    if title:
        clean_title = (
            title
            .split("|")[0]
            .split(" - ")[0]
            .split(" — ")[0]
            .strip()
        )

        if len(clean_title) > 45:
            clean_title = clean_title[:42] + "..."

        if clean_title:
            return clean_title

    return domain


def get_domain(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    if domain.startswith("www."):
        domain = domain[4:]

    return domain


def is_valid_url(url: str) -> bool:
    parsed = urlparse(url)

    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def extract_verdict_from_result(result: dict) -> str:
    return result.get("verdict", "Недостатньо даних")
