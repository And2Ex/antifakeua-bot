from html import escape

from config import BOT_USERNAME
from services.formatter import (
    clean_model_text,
    get_verdict_emoji,
    get_verdict_family,
    normalize_verdict_label,
)
from services.utils import escape_html


MARKABLE_FAMILIES = {"true", "mixed", "false", "uncertain"}


def build_public_check_url(public_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={public_id}"


def build_quick_mark(result: dict, *, public_id: str) -> str | None:
    if not result.get("public_mark_allowed", False):
        return None

    family = get_verdict_family(result)

    if family not in MARKABLE_FAMILIES:
        return None

    verdict = normalize_verdict_label(result.get("verdict"))
    emoji = get_verdict_emoji(result)
    line = f"{emoji} <b>{escape_html(verdict)}</b>"
    reason = clean_model_text(result.get("short_reason", "").strip())

    if family != "true" and reason:
        line += f" — {escape_html(reason)}"

    public_url = escape(build_public_check_url(public_id), quote=True)
    line += f' · <a href="{public_url}">AntiFakeUA</a>'

    return line
