import json
import re
from html import escape, unescape

from aiogram import Bot
from aiogram.types import (
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
)

from config import CHANNEL_ID
from services.formatter import clean_model_text, format_sources, format_verdict_line
from services.utils import escape_html


NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)
TELEGRAM_POST_LIMIT = 4000
TELEGRAM_CAPTION_LIMIT = 1024
PHOTO_VIDEO_MEDIA_TYPES = {"photo", "video"}
HTML_TAG_RE = re.compile(r"<[^>]*>")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")


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
    media_body = str(publication.get("media_body", "")).strip()

    if not title or not body:
        return None

    return {"title": title, "body": body, "media_body": media_body}


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


def telegram_text_length(html_text: str) -> int:
    """Count visible characters as Telegram does after HTML entities are parsed."""
    visible_text = HTML_TAG_RE.sub("", html_text)
    return len(unescape(visible_text))


def build_complete_excerpt(text: str, max_length: int) -> str:
    """Return only complete sentences; never publish an interrupted news sentence."""
    cleaned_text = clean_model_text(text).replace("\n", " ").strip()

    if len(cleaned_text) <= max_length:
        return cleaned_text

    sentences = [part.strip() for part in SENTENCE_SPLIT_RE.split(cleaned_text) if part.strip()]
    selected = []

    for sentence in sentences:
        candidate = " ".join([*selected, sentence])

        if len(candidate) > max_length:
            break

        selected.append(sentence)

    return " ".join(selected).strip()


def _render_channel_post(
    request,
    *,
    body_text: str | None = None,
    sources_limit: int,
    title_text: str | None = None,
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

    title = clean_model_text(title_text if title_text is not None else publication["title"])
    body = clean_model_text(body_text if body_text is not None else publication["body"])

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


def build_channel_post(request) -> str:
    """Build the ordinary channel message, keeping the full editorial draft."""
    publication = get_saved_publication(request)

    if publication is None:
        raise ValueError("Чернетку новинного допису ще не створено.")

    for sources_limit in (5, 3, 2, 1, 0):
        post_text = _render_channel_post(request, sources_limit=sources_limit)

        if telegram_text_length(post_text) <= TELEGRAM_POST_LIMIT:
            return post_text

    body = build_complete_excerpt(publication["body"], 1800)
    post_text = _render_channel_post(request, body_text=body, sources_limit=0)

    if telegram_text_length(post_text) <= TELEGRAM_POST_LIMIT:
        return post_text

    raise ValueError("Допис перевищує допустиму довжину Telegram.")


def build_media_caption(request) -> str:
    """Build a complete, readable caption within Telegram's 1024-character limit."""
    publication = get_saved_publication(request)

    if publication is None:
        raise ValueError("Чернетку новинного допису ще не створено.")

    full_post = _render_channel_post(request, sources_limit=5)

    if telegram_text_length(full_post) <= TELEGRAM_CAPTION_LIMIT:
        return full_post

    compact_body = publication.get("media_body") or build_complete_excerpt(
        publication["body"],
        420,
    )
    compact_body = build_complete_excerpt(compact_body, 450)

    for sources_limit in (3, 2, 1, 0):
        caption = _render_channel_post(
            request,
            body_text=compact_body,
            sources_limit=sources_limit,
        )

        if telegram_text_length(caption) <= TELEGRAM_CAPTION_LIMIT:
            return caption

    # The news title and source are more useful than a cut-off paragraph.
    caption = _render_channel_post(request, body_text="", sources_limit=0)

    if telegram_text_length(caption) <= TELEGRAM_CAPTION_LIMIT:
        return caption

    raise ValueError("Підпис до медіа перевищує допустиму довжину Telegram.")


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
