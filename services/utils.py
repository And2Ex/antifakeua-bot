import hashlib
from html import escape


MAX_TELEGRAM_MESSAGE_LENGTH = 4096


def is_meaningful_text(text: str) -> bool:
    text = text.strip()

    if len(text) < 5:
        return False

    words = text.split()

    if len(words) >= 2:
        return True

    if any(char.isdigit() for char in text):
        return False

    return len(text) >= 10


def normalize_text(text: str) -> str:
    return " ".join(text.strip().split())


def generate_text_hash(text: str) -> str:
    normalized_text = normalize_text(text).lower()

    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def truncate_text(text: str, max_length: int) -> str:
    text = text.strip()

    if len(text) <= max_length:
        return text

    return text[:max_length - 3].rstrip() + "..."


def escape_html(text: str | None) -> str:
    if text is None:
        return ""

    return escape(str(text), quote=True)
