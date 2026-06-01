from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions, Message, ReplyParameters

from database.db import add_request, add_user, get_connection, get_user, remember_content
from services.admin_notifications import notify_check_completed, notify_new_user
from keyboards.support import SUPPORT_ENTRY_KEYBOARD
from services.cache import get_cached_response, save_cached_response
from services.formatter import (
    extract_verdict_from_result,
    format_fact_check_response,
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


def get_link_source_type(link: str) -> str:
    normalized = normalize_domain(link)

    if normalized and normalized.startswith(("t.me/", "telegram.me/")):
        return "telegram"

    return "website"


def record_detected_sources(
    *,
    public_id: str,
    verdict: str,
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
        disable_notification=False,
    )


async def process_text_check(
    requester_message: Message,
    text: str,
    source_message: Message | None = None
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
        )

        record_detected_sources(
            public_id=public_id,
            verdict=cached_result["verdict"] or "Недостатньо даних",
            source_type=source_type,
            source_title=source_title,
            source_link=source_link,
            links=links,
            count_verdict=False,
        )

        await send_final_response(
            requester_message=requester_message,
            response=response,
            source_link=source_link,
            limit_message="",
            reply_parameters=reply_parameters,
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
    )

    record_detected_sources(
        public_id=public_id,
        verdict=verdict,
        source_type=source_type,
        source_title=source_title,
        source_link=source_link,
        links=links,
        count_verdict=True,
    )

    await send_final_response(
        requester_message=requester_message,
        response=response,
        source_link=source_link,
        limit_message=limit_message,
        reply_parameters=reply_parameters,
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
    )


@router.message(Command("check"))
async def check_command_handler(message: Message):
    if message.reply_to_message:
        replied_text = get_message_text(message.reply_to_message)

        if replied_text:
            await process_text_check(
                requester_message=message,
                source_message=message.reply_to_message,
                text=replied_text
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

    text = get_message_text(message)

    if not text:
        return

    await process_text_check(
        requester_message=message,
        text=text
    )


@router.message(F.photo | F.video | F.document | F.animation)
async def media_without_text_handler(message: Message):
    if message.chat.type != "private":
        return

    await message.answer(
        "<b>Зображення та відео поки що не аналізуються</b>\n\n"
        "Якщо матеріал містить текст новини, надішли його текстом.\n\n"
        "Для підтвердження підтримки через Monobank відкрий розділ "
        "<b>«Підтримати»</b> і саме там надішли скріншот переказу.",
        parse_mode="HTML",
    )
