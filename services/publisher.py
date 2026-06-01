import json
from html import escape

from aiogram import Bot
from aiogram.types import LinkPreviewOptions

from config import CHANNEL_ID
from services.formatter import clean_model_text, format_sources, format_verdict_line
from services.utils import escape_html, truncate_text


NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


def get_saved_result(request) -> dict | None:
    raw_result = request.get("result_json")

    if not raw_result:
        return None

    try:
        return json.loads(raw_result)
    except (TypeError, json.JSONDecodeError):
        return None


def build_source_reference(request) -> str | None:
    source_title = (request.get("source_title") or "").strip()
    source_link = (request.get("source_link") or "").strip()

    if not source_title or source_title == "Приватний чат":
        return None

    if source_link:
        return (
            "Опубліковано в: "
            f'<a href="{escape(source_link, quote=True)}">{escape_html(source_title)}</a>'
        )

    return f"Опубліковано в: {escape_html(source_title)}"


def build_channel_post(request) -> str:
    result = get_saved_result(request)

    if result is None:
        raise ValueError(
            "Цю перевірку створено у старому форматі. Перевір її повторно перед публікацією."
        )

    title = clean_model_text(result.get("publication_title", "").strip())
    summary = clean_model_text(result.get("summary", "").strip())
    blocks = result.get("blocks", [])
    parts = [format_verdict_line(result, include_reason=False)]

    if title:
        parts.extend(["", f"<b>{escape_html(title)}</b>"])

    source_reference = build_source_reference(request)

    if source_reference:
        parts.extend(["", source_reference])

    if summary:
        parts.extend(["", escape_html(summary)])

    if blocks:
        block_text = clean_model_text(str(blocks[0].get("text", "")).strip())

        if block_text and block_text.lower() not in summary.lower():
            parts.extend(["", escape_html(block_text)])

    sources = format_sources(result.get("sources", []))

    if sources:
        parts.extend(["", "<b>Джерела перевірки:</b>", *sources])

    parts.extend(["", "Перевірено через @AntiFakeUA_Bot"])

    return truncate_text("\n".join(parts).strip(), 4000)


async def publish_check_to_channel(bot: Bot, request):
    if not CHANNEL_ID:
        raise ValueError("CHANNEL_ID не заданий у .env")

    post_text = build_channel_post(request)

    return await bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        parse_mode="HTML",
        link_preview_options=NO_LINK_PREVIEW,
        disable_notification=True,
    )
