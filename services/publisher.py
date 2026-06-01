import json
from html import escape

from aiogram import Bot
from aiogram.types import (
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
)

from config import CHANNEL_ID
from services.formatter import clean_model_text, format_sources, format_verdict_line
from services.utils import escape_html, truncate_text


NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)
TELEGRAM_POST_LIMIT = 4000
TELEGRAM_CAPTION_LIMIT = 1024
PHOTO_VIDEO_MEDIA_TYPES = {"photo", "video"}


def get_saved_result(request) -> dict | None:
    raw_result = request.get("result_json")

    if not raw_result:
        return None

    try:
        return json.loads(raw_result)
    except (TypeError, json.JSONDecodeError):
        return None


def get_saved_publication(request) -> dict | None:
    raw_publication = request.get("publication_json")

    if not raw_publication:
        return None

    try:
        publication = json.loads(raw_publication)
    except (TypeError, json.JSONDecodeError):
        return None

    if not isinstance(publication, dict):
        return None

    title = str(publication.get("title", "")).strip()
    body = str(publication.get("body", "")).strip()

    if not title or not body:
        return None

    return {"title": title, "body": body}


def build_source_reference(request) -> str | None:
    """Return the original publication source as a linked name, without a label."""
    source_title = (request.get("source_title") or "").strip()
    source_link = (request.get("source_link") or "").strip()

    if not source_title or source_title == "Приватний чат":
        return None

    if source_link:
        return f'<a href="{escape(source_link, quote=True)}">{escape_html(source_title)}</a>'

    return escape_html(source_title)


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


def _render_channel_post(
    request,
    *,
    body_limit: int | None,
    sources_limit: int,
    title_limit: int | None = None,
) -> str:
    result = get_saved_result(request)
    publication = get_saved_publication(request)

    if result is None:
        raise ValueError("Результат перевірки не знайдено.")

    if publication is None:
        raise ValueError(
            "Чернетку новинного допису ще не створено. "
            "Відкрий перевірку через кнопку «Публікація»."
        )

    title = clean_model_text(publication["title"])
    body = clean_model_text(publication["body"])

    if title_limit is not None:
        title = truncate_text(title, title_limit)

    if body_limit is not None:
        body = truncate_text(body, body_limit)

    parts = [format_verdict_line(result, include_reason=False)]
    source_reference = build_source_reference(request)

    if source_reference:
        parts.append(source_reference)

    if title:
        parts.extend(["", f"<b>{escape_html(title)}</b>"])

    if body:
        parts.extend(["", escape_html(body)])

    sources = format_sources(result.get("sources", []), limit=sources_limit)

    if sources:
        parts.extend(["", "<b>Джерела перевірки:</b>", *sources])

    parts.extend(["", "Перевірено через @AntiFakeUA_Bot"])

    return "\n".join(parts).strip()


def _build_fitted_post(
    request,
    *,
    max_length: int,
    body_limits: tuple[int | None, ...],
    sources_limits: tuple[int, ...],
) -> str:
    for sources_limit in sources_limits:
        for body_limit in body_limits:
            post_text = _render_channel_post(
                request,
                body_limit=body_limit,
                sources_limit=sources_limit,
            )

            if len(post_text) <= max_length:
                return post_text

    fallback_text = _render_channel_post(
        request,
        body_limit=80,
        sources_limit=0,
        title_limit=100,
    )

    if len(fallback_text) <= max_length:
        return fallback_text

    raise ValueError("Допис перевищує допустиму довжину Telegram.")


def build_channel_post(request) -> str:
    """Build a full HTML channel message without cutting through HTML tags."""
    return _build_fitted_post(
        request,
        max_length=TELEGRAM_POST_LIMIT,
        body_limits=(None, 750, 550, 350, 180),
        sources_limits=(5, 3, 2, 1, 0),
    )


def build_media_caption(request) -> str:
    """Build a valid HTML caption fitting Telegram's 1024-character media limit."""
    return _build_fitted_post(
        request,
        max_length=TELEGRAM_CAPTION_LIMIT,
        body_limits=(650, 500, 360, 240, 140, 80),
        sources_limits=(3, 2, 1, 0),
    )


def build_input_media(item: dict, caption: str | None = None):
    media_type = item.get("type")
    file_id = item.get("file_id")

    if media_type == "photo":
        return InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML")

    if media_type == "video":
        return InputMediaVideo(media=file_id, caption=caption, parse_mode="HTML")

    if media_type == "document":
        return InputMediaDocument(media=file_id, caption=caption, parse_mode="HTML")

    return None


def validate_media_group(media_items: list[dict]) -> None:
    media_types = {item.get("type") for item in media_items}

    if media_types.issubset(PHOTO_VIDEO_MEDIA_TYPES):
        return

    if media_types == {"document"}:
        return

    raise ValueError(
        "Telegram не дозволяє опублікувати цей набір медіа одним альбомом. "
        "Опублікуй допис без медіа."
    )


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

    caption = build_media_caption(request)

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

    validate_media_group(media_items)
    album = []

    for index, item in enumerate(media_items[:10]):
        input_media = build_input_media(item, caption if index == 0 else None)

        if input_media is not None:
            album.append(input_media)

    if len(album) < 2:
        raise ValueError("Не вдалося сформувати альбом для публікації.")

    messages = await bot.send_media_group(
        chat_id=CHANNEL_ID,
        media=album,
        disable_notification=True,
    )
    return messages[0]
