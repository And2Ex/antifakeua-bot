from html import escape

from config import BOT_USERNAME
from services.formatter import VERDICT_EMOJIS, clean_model_text
from services.utils import escape_html


MARKABLE_VERDICTS = {"Правда", "Фейк", "Маніпуляція"}


def build_public_check_url(public_id: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={public_id}"


def build_quick_mark(result: dict, *, public_id: str) -> str | None:
    if not result.get("public_mark_allowed", False):
        return None

    verdict = clean_model_text(result.get("verdict", "").strip())

    if verdict not in MARKABLE_VERDICTS:
        return None

    emoji = VERDICT_EMOJIS.get(verdict, "ℹ️")
    line = f"{emoji} <b>{escape_html(verdict)}</b>"
    reason = clean_model_text(result.get("short_reason", "").strip())

    if verdict != "Правда" and reason:
        line += f" — {escape_html(reason)}"

    public_url = escape(build_public_check_url(public_id), quote=True)
    line += f' · <a href="{public_url}">AntiFakeUA</a>'

    return line
