import asyncio
import ipaddress
import json
import re
import socket
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import aiohttp

from services.utils import is_meaningful_text, normalize_text


MAX_RESPONSE_BYTES = 1_500_000
MAX_CONTENT_CHARS = 12_000
REQUEST_TIMEOUT_SECONDS = 15
MAX_REDIRECTS = 4
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0 Safari/537.36"
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
CONTENT_CLASS_MARKERS = {
    "tgme_widget_message_text",
    "article-body",
    "article__body",
    "entry-content",
    "post-content",
}


class PublicationHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title_parts: list[str] = []
        self.paragraphs: list[str] = []
        self.content_blocks: list[str] = []
        self.json_ld_blocks: list[str] = []
        self._capture_title = False
        self._capture_paragraph = False
        self._paragraph_parts: list[str] = []
        self._capture_json_ld = False
        self._json_ld_parts: list[str] = []
        self._content_depth = 0
        self._content_parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {key.lower(): (value or "") for key, value in attrs}

        if tag == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
            self._capture_json_ld = True
            self._json_ld_parts = []
            return

        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if self._content_depth:
            self._content_depth += 1
            if tag == "br":
                self._content_parts.append(" ")
        else:
            css_classes = attrs_dict.get("class", "").casefold()
            if any(marker in css_classes for marker in CONTENT_CLASS_MARKERS):
                self._content_depth = 1
                self._content_parts = []

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

        if tag == "script" and self._capture_json_ld:
            block = "".join(self._json_ld_parts).strip()
            if block:
                self.json_ld_blocks.append(block)
            self._capture_json_ld = False
            self._json_ld_parts = []
            return

        if tag in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
            return

        if self._skip_depth:
            return

        if self._content_depth:
            self._content_depth -= 1
            if self._content_depth == 0:
                content = normalize_text(" ".join(self._content_parts))
                if content:
                    self.content_blocks.append(content)
                self._content_parts = []

        if tag == "title":
            self._capture_title = False

        if tag == "p" and self._capture_paragraph:
            paragraph = normalize_text(" ".join(self._paragraph_parts))

            if paragraph:
                self.paragraphs.append(paragraph)

            self._capture_paragraph = False
            self._paragraph_parts = []

    def handle_data(self, data: str) -> None:
        if self._capture_json_ld:
            self._json_ld_parts.append(data)
            return

        if self._skip_depth:
            return

        cleaned = data.strip()

        if not cleaned:
            return

        if self._capture_title:
            self.title_parts.append(cleaned)

        if self._capture_paragraph:
            self._paragraph_parts.append(cleaned)

        if self._content_depth:
            self._content_parts.append(cleaned)


def _log_failure(url: str, reason: str) -> None:
    safe_url = url[:250].replace("\n", " ")
    print(f"LINK READER: {reason}; url={safe_url}")


def _is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False

    return ip.is_global and not (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _is_safe_public_url(url: str) -> bool:
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        _log_failure(url, "unsupported or missing URL scheme/host")
        return False

    host = parsed.hostname.strip("[]").lower()

    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        _log_failure(url, "local hostname blocked")
        return False

    try:
        ipaddress.ip_address(host)
        allowed = _is_public_address(host)
        if not allowed:
            _log_failure(url, "private or non-public literal IP blocked")
        return allowed
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        # Resolve IPv4 deliberately: several hosting environments do not have
        # a usable outbound IPv6 route even when sites advertise AAAA records.
        info = await loop.getaddrinfo(
            host,
            port,
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    except OSError as error:
        _log_failure(url, f"DNS lookup failed: {type(error).__name__}")
        return False

    addresses = {entry[4][0] for entry in info}
    allowed = bool(addresses) and all(_is_public_address(address) for address in addresses)

    if not allowed:
        _log_failure(url, "DNS returned non-public address")

    return allowed


def _clean_text(value: str | None) -> str:
    if not value:
        return ""

    text = unescape(value)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _walk_json_ld(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json_ld(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_json_ld(nested)


def _json_ld_candidates(blocks: list[str]) -> list[str]:
    candidates: list[str] = []

    for block in blocks:
        try:
            data = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            continue

        for item in _walk_json_ld(data):
            for key in ("headline", "description", "articleBody", "text"):
                cleaned = _clean_text(item.get(key))
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)

    return candidates


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
    source_candidates = [
        title,
        description,
        *parser.content_blocks,
        *_json_ld_candidates(parser.json_ld_blocks),
        *parser.paragraphs,
    ]

    for item in source_candidates:
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
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.7,en;q=0.6",
        "Cache-Control": "no-cache",
    }
    connector = aiohttp.TCPConnector(family=socket.AF_INET)

    try:
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
            connector=connector,
        ) as session:
            for _ in range(MAX_REDIRECTS + 1):
                if not await _is_safe_public_url(current_url):
                    return None

                async with session.get(current_url, allow_redirects=False) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")

                        if not location:
                            _log_failure(current_url, "redirect without Location header")
                            return None

                        current_url = urljoin(current_url, location)
                        continue

                    if response.status != 200:
                        _log_failure(current_url, f"HTTP status {response.status}")
                        return None

                    content_type = response.headers.get("Content-Type", "").lower()

                    if "html" not in content_type:
                        _log_failure(current_url, f"unsupported Content-Type: {content_type[:80]}")
                        return None

                    raw = await response.content.read(MAX_RESPONSE_BYTES + 1)

                    if len(raw) > MAX_RESPONSE_BYTES:
                        _log_failure(current_url, "page exceeds size limit")
                        return None

                    encoding = response.charset or "utf-8"
                    html = raw.decode(encoding, errors="replace")
                    extracted = _select_content(html, str(response.url))

                    if extracted is None:
                        _log_failure(current_url, "no meaningful publication text extracted")

                    return extracted

            _log_failure(url, "too many redirects")
            return None

    except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError) as error:
        _log_failure(current_url, f"request failed: {type(error).__name__}")
        return None
