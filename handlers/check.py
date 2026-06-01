import asyncio
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    ReplyParameters,
)

from config import ADMIN_IDS
from database.db import add_request, add_user, get_connection, get_user, remember_content
from services.admin_notifications import notify_check_completed, notify_new_user
from keyboards.support import SUPPORT_ENTRY_KEYBOARD
from services.cache import get_cached_response, save_cached_response
from services.formatter import (
    extract_verdict_from_result,
    format_fact_check_response,
    get_verdict_family,
)
from services.gpt import analyze_text
from services.limiter import check_and_use_text_limit
from services.progress import PROGRESS_FRAMES, run_with_progress, safe_delete_message
from services.reputation import (
    get_or_create_source,
    normalize_domain,
    record_source_mention,
    update_source_verdict,
)
from services.source_parser import extract_domains, extract_links
from services.utils import generate_text_hash, is_meaningful_text, normalize_text


router = Router()

NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)
MEDIA_GROUP_DELAY_SECONDS = 1.2
MEDIA_GROUPS: dict[str, dict] = {}


def get_message_media(message: Message) -> dict | None:
    if message.photo:
        photo = message.photo[-1]

        return {
            "type": "photo",
            "file_id": photo.file_id,
            "file_unique_id": photo.file_unique_id,
        }

    if message.video:
        return {
            "type": "video",
            "file_id": message.video.file_id,
            "file_unique_id": message.video.file_unique_id,
        }

    if message.animation:
        return {
            "type": "animation",
            "file_id": message.animation.file_id,
            "file_unique_id": message.animation.file_unique_id,
        }

    if message.document:
        return {
            "type": "document",
            "file_id": message.document.file_id,
            "file_unique_id": message.document.file_unique_id,
            "file_name": message.document.file_name,
        }

    return None


def merge_media_items(items: list[dict]) -> list[dict]:
    unique_items = []
    seen = set()

    for item in items:
        key = item.get("file_unique_id") or item.get("file_id")

        if not key or key in seen:
            continue

        unique_items.append(item)
        seen.add(key)

    return unique_items


def get_media_group_key(message: Message) -> str | None:
    if not message.media_group_id:
        return None

    return f"{message.chat.id}:{message.media_group_id}"


def get_message_text(message: Message) -> str | None:
    if message.text:
        return message.text

    if message.caption:
        return message.caption

    return None


def get_source_info(message: Message) -> tuple[str | None, str | None, str | None]:
    forward_origin = getattr(message, "forward_origin", None)

    if forward_origin is not None:
        origin_type = getattr(forward_origin, "type", None)

        if origin_type == "channel":
            chat = getattr(forward_origin, "chat", None)
            message_id = getattr(forward_origin, "message_id", None)

            title = getattr(chat, "title", None)
            username = getattr(chat, "username", None)

            source_link = None

            if username and message_id:
                source_link = f"https://t.me/{username}/{message_id}"

            return "forward_channel", title or "Переслано з каналу", source_link

        if origin_type == "chat":
            chat = getattr(forward_origin, "sender_chat", None)
            title = getattr(chat, "title", None)

            return "forward_chat", title or "Переслано з чату", None

        if origin_type == "user":
            sender_user = getattr(forward_origin, "sender_user", None)
            first_name = getattr(sender_user, "first_name", None)
            username = getattr(sender_user, "username", None)

            title = username or first_name or "Переслано від користувача"

            return "forward_user", title, None

        if origin_type == "hidden_user":
            sender_name = getattr(forward_origin, "sender_user_name", None)

            return "forward_hidden_user", sender_name or "Прихований відправник", None

        return "forward_unknown", "Переслане повідомлення", None

    chat = message.chat

    if chat.type == "private":
        return "private", "Приватний чат", None

    return chat.type, chat.title, None


def build_reply_parameters(source_message: Message, requester_message: Message) -> ReplyParameters | None:
    if source_message.chat.id != requester_message.chat.id:
        return None

    if source_message.message_id == requester_message.message_id:
        return None

    return ReplyParameters(message_id=source_message.message_id)


def build_extra_links(source_link: str | None) -> str:
    if not source_link:
        return ""

    return f'📌 <a href="{escape(source_link, quote=True)}">Оригінальний допис</a>'


def build_publication_entry_keyboard(public_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📰 Публікація",
                    callback_data=f"review_open:{public_id}",
                )
            ]
        ]
    )


def get_link_source_type(link: str) -> str:
    normalized = normalize_domain(link)

    if normalized and normalized.startswith(("t.me/", "telegram.me/")):
        return "telegram"

    return "website"


def record_detected_sources(
    *,
    public_id: str,
    verdict: str,
    verdict_family: str | None,
    source_type: str | None,
    source_title: str | None,
    source_link: str | None,
    links: list[str],
    count_verdict: bool,
) -> None:
    if not links and not source_title:
        return

    try:
        connection = get_connection()
        seen_keys = set()

        if source_title and source_title != "Приватний чат":
            key = normalize_domain(source_link) if source_link else source_title.lower()

            if key not in seen_keys:
                source_id = get_or_create_source(
                    connection,
                    name=source_title,
                    source_type=source_type or "telegram",
                    url=source_link,
                )
                record_source_mention(
                    connection,
                    source_id=source_id,
                    check_id=None,
                    url=source_link,
                    title=source_title,
                    stance="submitted_source",
                    verdict=verdict,
                )

                if count_verdict:
                    update_source_verdict(
                        connection,
                        source_id=source_id,
                        verdict=verdict,
                        verdict_family=verdict_family,
                    )

                seen_keys.add(key)

        for link in links:
            normalized = normalize_domain(link) or link.lower()

            if normalized in seen_keys:
                continue

            source_id = get_or_create_source(
                connection,
                name=normalized,
                source_type=get_link_source_type(link),
                url=link,
            )
            record_source_mention(
                connection,
                source_id=source_id,
                check_id=None,
                url=link,
                title=None,
                stance="mentioned",
                verdict=verdict,
            )

            if count_verdict:
                update_source_verdict(
                    connection,
                    source_id=source_id,
                    verdict=verdict,
                    verdict_family=verdict_family,
                )

            seen_keys.add(normalized)

        connection.commit()
        connection.close()

    except Exception as error:
        print(f"SOURCE REPUTATION ERROR: {error}")


async def send_final_response(
    requester_message: Message,
    response: str,
    source_link: str | None,
    limit_message: str = "",
    reply_parameters: ReplyParameters | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
):
    parts = [
        response,
        build_extra_links(source_link),
    ]

    if limit_message:
        parts.append(limit_message)

    await requester_message.answer(
        "\n\n".join(part for part in parts if part).strip(),
        parse_mode="HTML",
        link_preview_options=NO_LINK_PREVIEW,
        reply_parameters=reply_parameters,
        reply_markup=reply_markup,
        disable_notification=False,
    )


async def process_text_check(
    requester_message: Message,
    text: str,
    source_message: Message | None = None,
    media: list[dict] | None = None,
    media_group_id: str | None = None,
):
    source_message = source_message or requester_message
    user = requester_message.from_user
    text = normalize_text(text)

    if not is_meaningful_text(text):
        await requester_message.answer(
            "<b>Немає що перевіряти</b>\n\n"
            "Надішли текст новини, заяву або конкретне твердження.",
            parse_mode="HTML",
        )
        return

    is_new_user = get_user(user.id) is None

    add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )

    if is_new_user:
        await notify_new_user(
            requester_message.bot,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

    source_type, source_title, source_link = get_source_info(source_message)

    links = extract_links(text)

    if source_link:
        links.append(source_link)

    links = list(dict.fromkeys(links))
    domains = extract_domains(links)

    links_text = ", ".join(links) if links else None
    domains_text = ", ".join(domains) if domains else None
    reply_parameters = build_reply_parameters(source_message, requester_message)

    remember_content(
        content_hash=generate_text_hash(text),
        original_context=text[:500],
        original_url=source_link or (links[0] if links else None),
    )

    cached_result = get_cached_response(text)

    # Re-run legacy cached checks once so new flexible verdicts can be generated.
    if cached_result is not None and not cached_result["result"].get("verdict_family"):
        cached_result = None

    if cached_result is not None:
        cached_analysis = cached_result["result"]
        response = format_fact_check_response(cached_analysis)
        public_id = add_request(
            user_id=user.id,
            request_text=text,
            response_text=response,
            source_type=source_type,
            source_title=source_title,
            source_link=source_link,
            detected_links=links_text,
            detected_domains=domains_text,
            verdict=cached_result["verdict"],
            from_cache=True,
            result=cached_analysis,
            is_publishable=bool(cached_analysis.get("public_mark_allowed", False)),
            media=media,
            media_group_id=media_group_id,
        )

        record_detected_sources(
            public_id=public_id,
            verdict=cached_result["verdict"] or "Недостатньо даних",
            verdict_family=get_verdict_family(cached_analysis),
            source_type=source_type,
            source_title=source_title,
            source_link=source_link,
            links=links,
            count_verdict=False,
        )

        publication_keyboard = None

        if user.id in ADMIN_IDS and bool(cached_analysis.get("public_mark_allowed", False)):
            publication_keyboard = build_publication_entry_keyboard(public_id)

        await send_final_response(
            requester_message=requester_message,
            response=response,
            source_link=source_link,
            limit_message="",
            reply_parameters=reply_parameters,
            reply_markup=publication_keyboard,
        )

        await notify_check_completed(
            requester_message.bot,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            verdict=cached_result["verdict"],
            source_title=source_title,
            from_cache=True,
            text=text,
            public_id=public_id,
            is_publishable=bool(cached_analysis.get("public_mark_allowed", False)),
        )
        return

    limit_allowed, limit_message = check_and_use_text_limit(user.id)

    if not limit_allowed:
        await requester_message.answer(
            limit_message,
            parse_mode="HTML",
            reply_markup=SUPPORT_ENTRY_KEYBOARD,
        )
        return

    status_message = await requester_message.answer(
        PROGRESS_FRAMES[0],
        reply_parameters=reply_parameters,
        disable_notification=True,
    )

    try:
        result = await run_with_progress(
            status_message=status_message,
            work=analyze_text(text),
        )
    finally:
        await safe_delete_message(status_message)

    base_response = format_fact_check_response(result)
    response = base_response
    verdict = extract_verdict_from_result(result)

    save_cached_response(
        text=text,
        response=base_response,
        verdict=verdict,
        result=result,
    )

    public_id = add_request(
        user_id=user.id,
        request_text=text,
        response_text=response,
        source_type=source_type,
        source_title=source_title,
        source_link=source_link,
        detected_links=links_text,
        detected_domains=domains_text,
        verdict=verdict,
        from_cache=False,
        result=result,
        is_publishable=bool(result.get("public_mark_allowed", False)),
        media=media,
        media_group_id=media_group_id,
    )

    record_detected_sources(
        public_id=public_id,
        verdict=verdict,
        verdict_family=get_verdict_family(result),
        source_type=source_type,
        source_title=source_title,
        source_link=source_link,
        links=links,
        count_verdict=True,
    )

    publication_keyboard = None

    if user.id in ADMIN_IDS and bool(result.get("public_mark_allowed", False)):
        publication_keyboard = build_publication_entry_keyboard(public_id)

    await send_final_response(
        requester_message=requester_message,
        response=response,
        source_link=source_link,
        limit_message=limit_message,
        reply_parameters=reply_parameters,
        reply_markup=publication_keyboard,
    )

    await notify_check_completed(
        requester_message.bot,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        verdict=verdict,
        source_title=source_title,
        from_cache=False,
        text=text,
        public_id=public_id,
        is_publishable=bool(result.get("public_mark_allowed", False)),
    )




async def process_media_group_later(group_key: str):
    await asyncio.sleep(MEDIA_GROUP_DELAY_SECONDS)

    group = MEDIA_GROUPS.pop(group_key, None)

    if not group:
        return

    text = group.get("caption")
    requester_message = group.get("message")

    if not text or requester_message is None:
        return

    await process_text_check(
        requester_message=requester_message,
        source_message=requester_message,
        text=text,
        media=merge_media_items(group.get("media", [])),
        media_group_id=str(group.get("media_group_id") or ""),
    )


def remember_media_group_message(message: Message) -> bool:
    group_key = get_media_group_key(message)

    if not group_key:
        return False

    group = MEDIA_GROUPS.setdefault(
        group_key,
        {
            "caption": None,
            "message": None,
            "media": [],
            "media_group_id": message.media_group_id,
            "task": None,
        },
    )

    media_item = get_message_media(message)

    if media_item:
        group["media"].append(media_item)

    if message.caption:
        group["caption"] = message.caption
        group["message"] = message

    task = group.get("task")

    if task is not None and not task.done():
        task.cancel()

    group["task"] = asyncio.create_task(process_media_group_later(group_key))

    return True


@router.message(Command("check"))
async def check_command_handler(message: Message):
    if message.reply_to_message:
        replied_text = get_message_text(message.reply_to_message)

        if replied_text:
            media_item = get_message_media(message.reply_to_message)
            media = [media_item] if media_item else None

            await process_text_check(
                requester_message=message,
                source_message=message.reply_to_message,
                text=replied_text,
                media=media,
                media_group_id=message.reply_to_message.media_group_id,
            )
            return

    parts = message.text.split(maxsplit=1)

    if len(parts) == 2:
        await process_text_check(
            requester_message=message,
            text=parts[1]
        )
        return

    await message.answer(
        "<b>Як користуватись командою /check</b>\n\n"
        "У групі відповідай <code>/check</code> на повідомлення, яке треба перевірити.\n\n"
        "Або напиши так:\n"
        "<code>/check мобілізацію продовжено</code>",
        parse_mode="HTML",
    )


@router.message(F.text)
@router.message(F.caption)
async def check_text_or_caption_handler(message: Message):
    if message.chat.type != "private":
        return

    if message.media_group_id and remember_media_group_message(message):
        return

    text = get_message_text(message)

    if not text:
        return

    media_item = get_message_media(message)
    media = [media_item] if media_item else None

    await process_text_check(
        requester_message=message,
        text=text,
        media=media,
        media_group_id=message.media_group_id,
    )


@router.message(F.photo | F.video | F.document | F.animation)
async def media_without_text_handler(message: Message):
    if message.chat.type != "private":
        return

    if message.media_group_id and remember_media_group_message(message):
        return

    await message.answer(
        "<b>Зображення та відео поки що не аналізуються</b>\n\n"
        "Якщо медіа має опис із новиною, бот перевірить саме цей опис як текст. "
        "Якщо новина написана тільки на зображенні або у відео, скопіюй її текст і надішли окремим повідомленням.\n\n"
        "Для підтвердження підтримки через Monobank відкрий розділ "
        "<b>«Підтримати»</b> і саме там надішли скріншот переказу.",
        parse_mode="HTML",
    )
