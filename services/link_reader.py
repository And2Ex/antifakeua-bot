import asyncio
import ipaddress
import re
import socket
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import aiohttp

from services.utils import is_meaningful_text, normalize_text


MAX_RESPONSE_BYTES = 1_500_000
MAX_CONTENT_CHARS = 12_000
REQUEST_TIMEOUT_SECONDS = 12
MAX_REDIRECTS = 4
USER_AGENT = (
    "Mozilla/5.0 (compatible; AntiFakeUA_Bot/1.0; "
    "+https://t.me/AntiFakeUA_Bot)"
)
GENERIC_PAGE_MARKERS = {
    "instagram",
    "login • instagram",
    "log in • instagram",
    "facebook – log in or sign up",
    "x. it’s what’s happening",
    "page not found",
    "access denied",
    "just a moment...",
}


class PublicationHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.paragraphs: list[str] = []
        self._capture_title = False
        self._capture_paragraph = False
        self._paragraph_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): (value or "") for key, value in attrs}

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag == "meta":
            key = (
                attrs_dict.get("property")
                or attrs_dict.get("name")
                or attrs_dict.get("itemprop")
            ).strip().lower()
            content = attrs_dict.get("content", "").strip()

            if key and content:
                self.meta.setdefault(key, content)

        if tag == "title":
            self._capture_title = True

        if tag == "p":
            self._capture_paragraph = True
            self._paragraph_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if tag == "title":
            self._capture_title = False

        if tag == "p" and self._capture_paragraph:
            paragraph = normalize_text(" ".join(self._paragraph_parts))

            if paragraph:
                self.paragraphs.append(paragraph)

            self._capture_paragraph = False
            self._paragraph_parts = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return

        cleaned = data.strip()

        if not cleaned:
            return

        if self._capture_title:
            self.title_parts.append(cleaned)

        if self._capture_paragraph:
            self._paragraph_parts.append(cleaned)


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _is_safe_public_url(url: str) -> bool:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False

    host = parsed.hostname.strip("[]").lower()

    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False

    try:
        ipaddress.ip_address(host)
        return _is_public_address(host)
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        info = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return False

    return bool(info) and all(_is_public_address(entry[4][0]) for entry in info)


def _clean_text(value: str | None) -> str:
    if not value:
        return ""

    text = unescape(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _select_content(html: str, final_url: str) -> dict | None:
    parser = PublicationHTMLParser()

    try:
        parser.feed(html)
    except Exception:
        return None

    title = _clean_text(
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or " ".join(parser.title_parts)
    )
    description = _clean_text(
        parser.meta.get("og:description")
        or parser.meta.get("twitter:description")
        or parser.meta.get("description")
    )
    site_name = _clean_text(parser.meta.get("og:site_name"))

    candidates: list[str] = []

    for item in [title, description, *parser.paragraphs]:
        cleaned = _clean_text(item)

        if not cleaned or cleaned in candidates:
            continue

        lowered = cleaned.casefold()

        if lowered in GENERIC_PAGE_MARKERS:
            continue

        candidates.append(cleaned)

    content = normalize_text("\n\n".join(candidates))[:MAX_CONTENT_CHARS]

    if not content or not is_meaningful_text(content):
        return None

    domain = urlparse(final_url).netloc.removeprefix("www.")
    source_title = site_name or domain

    return {
        "url": final_url,
        "source_title": source_title,
        "title": title,
        "content": content,
    }


async def fetch_publication_content(url: str) -> dict | None:
    current_url = url
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "uk,en;q=0.8",
    }

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            for _ in range(MAX_REDIRECTS + 1):
                if not await _is_safe_public_url(current_url):
                    return None

                async with session.get(current_url, allow_redirects=False) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")

                        if not location:
                            return None

                        current_url = urljoin(current_url, location)
                        continue

                    if response.status != 200:
                        return None

                    content_type = response.headers.get("Content-Type", "").lower()

                    if "html" not in content_type:
                        return None

                    raw = await response.content.read(MAX_RESPONSE_BYTES + 1)

                    if len(raw) > MAX_RESPONSE_BYTES:
                        return None

                    encoding = response.charset or "utf-8"
                    html = raw.decode(encoding, errors="replace")

                    return _select_content(html, str(response.url))

    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError):
        return None

    return None
