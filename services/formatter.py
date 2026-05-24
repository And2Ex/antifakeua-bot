from urllib.parse import urlparse

from services.utils import escape_html


VERDICT_EMOJIS = {
    "Правда": "✅",
    "Фейк": "❌",
    "Маніпуляція": "⚠️",
    "Недостатньо даних": "ℹ️",
    "Інше": "ℹ️",
}

BLOCK_EMOJIS = {
    "Правда": "✅",
    "Фейк": "❌",
    "Маніпуляція": "⚠️",
    "Уточнення": "ℹ️",
    "Недостатньо даних": "❔",
}


def format_fact_check_response(result: dict) -> str:
    verdict = result.get("verdict", "Недостатньо даних")
    summary = result.get("summary", "").strip()
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

    for block in blocks[:3]:
        block_type = block.get("type", "Уточнення")
        block_text = block.get("text", "").strip()

        if not block_text:
            continue

        block_emoji = BLOCK_EMOJIS.get(block_type, "ℹ️")

        parts.extend([
            "",
            f"{block_emoji} <b>{escape_html(block_type)}:</b>",
            escape_html(block_text),
        ])

    formatted_sources = format_sources(sources)

    if formatted_sources:
        parts.append("")
        parts.append("<b>Джерела:</b>")
        parts.extend(formatted_sources)

    return "\n".join(parts).strip()


def format_sources(sources: list[dict], limit: int = 5) -> list[str]:
    formatted_sources = []
    used_urls = set()

    for source in sources[:limit]:
        title = source.get("title", "").strip()
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
