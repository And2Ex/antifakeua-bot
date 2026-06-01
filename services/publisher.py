import json
from html import escape

from aiogram import Bot
from aiogram.types import InputMediaAnimation, InputMediaDocument, InputMediaPhoto, InputMediaVideo, LinkPreviewOptions

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


def get_saved_media(request) -> list[dict]:
    raw_media = request.get("media_json")

    if not raw_media:
        return []

    try:
        media = json.loads(raw_media)
    except (TypeError, json.JSONDecodeError):
        return []

    if not isinstance(media, list):
        return []

    return [item for item in media if isinstance(item, dict) and item.get("file_id")]


def build_media_caption(post_text: str) -> str:
    if len(post_text) <= 1024:
        return post_text

    return truncate_text(post_text, 1000)


def build_input_media(item: dict, caption: str | None = None):
    media_type = item.get("type")
    file_id = item.get("file_id")

    if media_type == "photo":
        return InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML")

    if media_type == "video":
        return InputMediaVideo(media=file_id, caption=caption, parse_mode="HTML")

    if media_type == "animation":
        return InputMediaAnimation(media=file_id, caption=caption, parse_mode="HTML")

    if media_type == "document":
        return InputMediaDocument(media=file_id, caption=caption, parse_mode="HTML")

    return None


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


async def publish_check_to_channel(bot: Bot, request, include_media: bool = False):
    if not CHANNEL_ID:
        raise ValueError("CHANNEL_ID не заданий у .env")

    post_text = build_channel_post(request)
    media_items = get_saved_media(request) if include_media else []

    if not media_items:
        return await bot.send_message(
            chat_id=CHANNEL_ID,
            text=post_text,
            parse_mode="HTML",
            link_preview_options=NO_LINK_PREVIEW,
            disable_notification=True,
        )

    caption = build_media_caption(post_text)

    if len(media_items) == 1:
        item = media_items[0]
        media_type = item.get("type")
        file_id = item.get("file_id")

        if media_type == "photo":
            return await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=file_id,
                caption=caption,
                parse_mode="HTML",
                disable_notification=True,
            )

        if media_type == "video":
            return await bot.send_video(
                chat_id=CHANNEL_ID,
                video=file_id,
                caption=caption,
                parse_mode="HTML",
                disable_notification=True,
            )

        if media_type == "animation":
            return await bot.send_animation(
                chat_id=CHANNEL_ID,
                animation=file_id,
                caption=caption,
                parse_mode="HTML",
                disable_notification=True,
            )

        if media_type == "document":
            return await bot.send_document(
                chat_id=CHANNEL_ID,
                document=file_id,
                caption=caption,
                parse_mode="HTML",
                disable_notification=True,
            )

    album = []

    for index, item in enumerate(media_items[:10]):
        input_media = build_input_media(item, caption if index == 0 else None)

        if input_media is not None:
            album.append(input_media)

    if album:
        messages = await bot.send_media_group(
            chat_id=CHANNEL_ID,
            media=album,
            disable_notification=True,
        )
        return messages[0]

    return await bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        parse_mode="HTML",
        link_preview_options=NO_LINK_PREVIEW,
        disable_notification=True,
    )
