import asyncio
from html import escape
from time import monotonic
from typing import Awaitable, TypeVar

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions, Message, ReplyParameters

from database.db import add_request, add_user, get_connection, remember_content
from services.cache import get_cached_response, save_cached_response
from services.formatter import (
    extract_verdict_from_result,
    format_fact_check_response,
)
from services.gpt import analyze_text
from services.limiter import check_and_use_text_limit
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

T = TypeVar("T")

PROGRESS_STATUS_ENABLED = True
PROGRESS_MIN_SECONDS = 4.0
PROGRESS_STEP_SECONDS = 1.3
PROGRESS_DELETE_STATUS = True

PROGRESS_STAGES = [
    "🔎 Аналізую твердження...",
    "🌐 Зіставляю з відкритими джерелами...",
    "🧠 Узагальнюю результат перевірки...",
]


async def safe_edit_message(message: Message, text: str):
    try:
        await message.edit_text(text)
    except Exception as error:
        error_text = str(error).lower()

        if "message is not modified" in error_text:
            return

        print(f"PROGRESS EDIT ERROR: {error}")


async def safe_delete_message(message: Message):
    try:
        await message.delete()
    except Exception as error:
        print(f"PROGRESS DELETE ERROR: {error}")


async def run_with_progress(status_message: Message, work: Awaitable[T]) -> T:
    if not PROGRESS_STATUS_ENABLED:
        return await work

    task = asyncio.create_task(work)
    started_at = monotonic()
    stage_index = 0
    last_stage_text = status_message.text or ""

    try:
        while True:
            elapsed = monotonic() - started_at
            min_time_passed = elapsed >= PROGRESS_MIN_SECONDS

            if task.done() and min_time_passed:
                break

            stage_text = PROGRESS_STAGES[stage_index % len(PROGRESS_STAGES)]

            if stage_text != last_stage_text:
                await safe_edit_message(status_message, stage_text)
                last_stage_text = stage_text

            stage_index += 1
            await asyncio.sleep(max(PROGRESS_STEP_SECONDS, 0.2))

        return await task

    finally:
        if PROGRESS_DELETE_STATUS:
            await safe_delete_message(status_message)


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


async def make_public_link(message: Message, public_id: str) -> str:
    bot_info = await message.bot.get_me()

    return f"https://t.me/{bot_info.username}?start={public_id}"


def build_reply_parameters(source_message: Message, requester_message: Message) -> ReplyParameters | None:
    if source_message.chat.id != requester_message.chat.id:
        return None

    if source_message.message_id == requester_message.message_id:
        return None

    return ReplyParameters(message_id=source_message.message_id)


def build_extra_links(public_link: str, source_link: str | None) -> str:
    parts = []

    if source_link:
        parts.append(
            f'📌 <a href="{escape(source_link, quote=True)}">Оригінальний допис</a>'
        )

    parts.append(
        f'🔗 <a href="{escape(public_link, quote=True)}">Публічна перевірка</a>'
    )

    return "\n".join(parts)


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
    public_link: str,
    source_link: str | None,
    limit_message: str = "",
    reply_parameters: ReplyParameters | None = None,
):
    parts = [
        response,
        build_extra_links(public_link, source_link),
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
            "Надішли текст новини або твердження для перевірки."
        )
        return

    add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
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
        response = cached_result["response_text"]
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
            from_cache=True
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

        public_link = await make_public_link(requester_message, public_id)

        await send_final_response(
            requester_message=requester_message,
            response=response,
            public_link=public_link,
            source_link=source_link,
            limit_message="🔁 Цю новину вже перевіряли раніше. Ліміт не списано.",
            reply_parameters=reply_parameters,
        )
        return

    limit_allowed, limit_message = check_and_use_text_limit(user.id)

    if not limit_allowed:
        await requester_message.answer(limit_message)
        return

    status_message = await requester_message.answer(
        "🔎 Аналізую твердження...",
        reply_parameters=reply_parameters,
        disable_notification=True,
    )

    result = await run_with_progress(
        status_message=status_message,
        work=analyze_text(text),
    )

    base_response = format_fact_check_response(result)
    response = base_response
    verdict = extract_verdict_from_result(result)

    save_cached_response(
        text=text,
        response=base_response,
        verdict=verdict
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
        from_cache=False
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

    public_link = await make_public_link(requester_message, public_id)

    await send_final_response(
        requester_message=requester_message,
        response=response,
        public_link=public_link,
        source_link=source_link,
        limit_message=limit_message,
        reply_parameters=reply_parameters,
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
        "Щоб перевірити текст, надішли:\n\n"
        "/check текст твердження\n\n"
        "Або відповідай командою /check на повідомлення з текстом."
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
    # Порожні медіа-повідомлення мовчки ігноруємо.
    # У Telegram альбоми та переслані дописи можуть приходити кількома update-ами,
    # і відповідь на кожен порожній update створює спам у чаті.
    return
