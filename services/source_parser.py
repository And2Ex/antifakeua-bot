import re
from urllib.parse import urlparse


URL_PATTERN = re.compile(
    r"(https?://[^\s]+|(?:www\.)?(?:t\.me|telegram\.me|instagram\.com|threads\.net|threads\.com|facebook\.com|fb\.watch|x\.com|twitter\.com)/[^\s]+)",
    re.IGNORECASE
)


def extract_links(text: str) -> list[str]:
    links = URL_PATTERN.findall(text)
    cleaned_links = []

    for link in links:
        cleaned_link = link.strip(".,!?()[]{}<>\"'")

        if not cleaned_link.lower().startswith(("http://", "https://")):
            cleaned_link = f"https://{cleaned_link}"

        cleaned_links.append(cleaned_link)

    return list(dict.fromkeys(cleaned_links))


def extract_domains(links: list[str]) -> list[str]:
    domains = []

    for link in links:
        try:
            parsed = urlparse(link)
            domain = parsed.netloc.lower()

            if domain.startswith("www."):
                domain = domain[4:]

            if domain in {"t.me", "telegram.me"}:
                channel = parsed.path.strip("/").split("/", 1)[0].lower()

                if channel:
                    domain = f"{domain}/{channel}"

            if domain:
                domains.append(domain)

        except Exception:
            continue

    return list(dict.fromkeys(domains))


def is_standalone_link_request(text: str) -> bool:
    """Return True when the user's whole submission is a single URL."""
    links = extract_links(text)

    if len(links) != 1:
        return False

    remaining = URL_PATTERN.sub("", text).strip(" \n\t.,!?()[]{}<>\"'")

    return not remaining
