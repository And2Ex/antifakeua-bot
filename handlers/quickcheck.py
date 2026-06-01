import asyncio
from html import escape

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    ChatAdministratorRights,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    LinkPreviewOptions,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from database.db import (
    add_request,
    add_user,
    complete_quick_check,
    remember_content,
    get_channel_setting,
    reserve_quick_check,
    save_channel_setting,
    set_channel_mode,
)
from services.cache import get_cached_response, save_cached_response
from services.source_parser import extract_domains, extract_links
from services.formatter import format_fact_check_response
from services.gpt import analyze_text
from services.limiter import check_and_use_text_limit
from services.progress import PROGRESS_FRAMES, run_with_progress, safe_delete_message, safe_edit_message
from services.news_filter import classify_channel_post
from services.quick_verdict import build_quick_mark
from services.utils import generate_text_hash, normalize_text


router = Router()

NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)
CHANNEL_REQUEST_ID = 28001
CONTROL_DELETE_SECONDS = 2
PENDING_GROUP_COMMANDS: dict[tuple[int, int], int] = {}


CHANNEL_ADMIN_RIGHTS = ChatAdministratorRights(
    is_anonymous=False,
    can_manage_chat=True,
    can_delete_messages=False,
    can_manage_video_chats=False,
    can_restrict_members=False,
    can_promote_members=False,
    can_change_info=False,
    can_invite_users=False,
    can_post_stories=False,
    can_edit_stories=False,
    can_delete_stories=False,
    can_post_messages=True,
    can_edit_messages=False,
)


def get_post_text(message: Message) -> str | None:
    return message.text or message.caption


def get_post_source_info(message: Message) -> tuple[str, str, str | None]:
    title = message.chat.title or "Telegram-канал"
    username = message.chat.username

    if username:
        source_link = f"https://t.me/{username}/{message.message_id}"
    elif message.chat.type == "channel" and str(message.chat.id).startswith("-100"):
        internal_id = str(message.chat.id)[4:]
        source_link = f"https://t.me/c/{internal_id}/{message.message_id}"
    else:
        source_link = None

    return message.chat.type, title, source_link


def is_own_marker(text: str) -> bool:
    lowered = text.lower()
    return "antifakeua" in lowered


def channel_picker_keyboard() -> ReplyKeyboardMarkup:
    request_chat = KeyboardButtonRequestChat(
        request_id=CHANNEL_REQUEST_ID,
        chat_is_channel=True,
        user_administrator_rights=CHANNEL_ADMIN_RIGHTS,
        bot_administrator_rights=CHANNEL_ADMIN_RIGHTS,
        request_title=True,
        request_username=True,
    )

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Обрати канал", request_chat=request_chat)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def toggle_keyboard(chat_id: int, mode: str) -> InlineKeyboardMarkup:
    target_mode = "manual" if mode == "auto" else "auto"
    text = (
        "Вимкнути автоматичну перевірку"
        if mode == "auto"
        else "Увімкнути автоматичну перевірку"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=f"quick_toggle:{chat_id}:{target_mode}")]
        ]
    )


def build_settings_text(chat_title: str, mode: str) -> str:
    status = "увімкнена" if mode == "auto" else "вимкнена"

    return (
        "<b>QuickCheck для каналу</b>\n\n"
        f"<b>Канал:</b> {escape(chat_title)}\n"
        f"<b>Автоматична коротка перевірка:</b> {status}\n\n"
        "У режимі автоматичної перевірки бот реагує лише на дописи, "
        "схожі на новини або фактичні твердження. Рекламні й неперевірювані "
        "повідомлення залишаються без позначки.\n\n"
        "Нові автоматичні перевірки використовують доступний баланс адміністратора, який увімкнув режим. "
        "Посилання AntiFakeUA у короткій позначці відкриває повний висновок і джерела."
    )


async def delete_later(message: Message | None, delay: float = CONTROL_DELETE_SECONDS) -> None:
    if message is None:
        return

    await asyncio.sleep(delay)

    try:
        await message.delete()
    except Exception:
        return


async def get_chat_member_safely(message_or_callback, chat_id: int, user_id: int):
    try:
        return await message_or_callback.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except Exception as error:
        print(
            "QUICKCHECK MEMBER LOOKUP ERROR: "
            f"chat_id={chat_id}, user_id={user_id}, "
            f"{type(error).__name__}: {error}"
        )
        return None


def is_administrator_status(status) -> bool:
    return status in {
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
        "administrator",
        "creator",
    }


async def user_is_chat_admin(message_or_callback, chat_id: int, user_id: int) -> bool:
    member = await get_chat_member_safely(message_or_callback, chat_id, user_id)
    return member is not None and is_administrator_status(member.status)


async def bot_is_chat_admin(message_or_callback, chat_id: int) -> bool:
    try:
        bot_info = await message_or_callback.bot.get_me()
    except Exception as error:
        print(f"QUICKCHECK BOT LOOKUP ERROR: {type(error).__name__}: {error}")
        return False

    member = await get_chat_member_safely(message_or_callback, chat_id, bot_info.id)
    return member is not None and is_administrator_status(member.status)


async def bot_can_post_to_channel(message_or_callback, chat_id: int) -> bool:
    try:
        bot_info = await message_or_callback.bot.get_me()
    except Exception as error:
        print(f"QUICKCHECK BOT LOOKUP ERROR: {type(error).__name__}: {error}")
        return False

    member = await get_chat_member_safely(message_or_callback, chat_id, bot_info.id)
    return (
        member is not None
        and is_administrator_status(member.status)
        and bool(getattr(member, "can_post_messages", False))
    )


async def show_channel_settings(message: Message, chat_id: int, chat_title: str, chat_type: str, user_id: int) -> None:
    current = get_channel_setting(chat_id)

    if current is None:
        save_channel_setting(
            chat_id=chat_id,
            chat_title=chat_title,
            chat_type=chat_type,
            enabled_by=user_id,
            mode="manual",
        )
        mode = "manual"
    else:
        mode = current["mode"]
        save_channel_setting(
            chat_id=chat_id,
            chat_title=chat_title,
            chat_type=chat_type,
            enabled_by=current["enabled_by"],
            mode=mode,
        )

    await message.answer(
        build_settings_text(chat_title, mode),
        parse_mode="HTML",
        reply_markup=toggle_keyboard(chat_id, mode),
        link_preview_options=NO_LINK_PREVIEW,
        disable_notification=True,
    )


@router.message(Command("quickcheck"))
async def quickcheck_settings_handler(message: Message):
    user = message.from_user

    if user is None:
        return

    add_user(user_id=user.id, username=user.username, first_name=user.first_name)

    if message.chat.type == "private":
        await message.answer(
            "<b>QuickCheck для каналів</b>\n\n"
            "Обери канал, у якому ти є адміністратором і де бот доданий з правом публікувати повідомлення.",
            parse_mode="HTML",
            reply_markup=channel_picker_keyboard(),
        )
        return

    if message.chat.type not in {"group", "supergroup"}:
        return

    if not await bot_is_chat_admin(message, message.chat.id):
        await message.answer(
            "Спочатку додай бота адміністратором цієї групи. "
            "Це потрібно, щоб бот міг підтвердити права адміністратора "
            "та бачити нові повідомлення для автоматичної перевірки."
        )
        return

    if not await user_is_chat_admin(message, message.chat.id, user.id):
        await message.answer("Це налаштування може змінювати лише адміністратор цієї групи.")
        return

    PENDING_GROUP_COMMANDS[(message.chat.id, user.id)] = message.message_id
    await show_channel_settings(
        message,
        chat_id=message.chat.id,
        chat_title=message.chat.title or "Група",
        chat_type=message.chat.type,
        user_id=user.id,
    )


@router.message(F.chat_shared)
async def selected_channel_handler(message: Message):
    shared = message.chat_shared
    user = message.from_user

    if shared is None or shared.request_id != CHANNEL_REQUEST_ID or user is None:
        return

    # Спершу перевіряємо права самого бота. Telegram гарантує коректну
    # перевірку адміністратора через getChatMember лише тоді, коли бот
    # є адміністратором цього ж каналу.
    if not await bot_can_post_to_channel(message, shared.chat_id):
        await message.answer(
            "Спочатку додай бота адміністратором цього каналу та дозволь "
            "йому публікувати повідомлення. Після цього обери канал ще раз.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    if not await user_is_chat_admin(message, shared.chat_id, user.id):
        await message.answer(
            "Не вдалося підтвердити, що ти є адміністратором цього каналу.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    title = shared.title or (f"@{shared.username}" if shared.username else "Обраний канал")

    await message.answer("Канал обрано.", reply_markup=ReplyKeyboardRemove(), disable_notification=True)
    await show_channel_settings(
        message,
        chat_id=shared.chat_id,
        chat_title=title,
        chat_type="channel",
        user_id=user.id,
    )


@router.callback_query(F.data.startswith("quick_toggle:"))
async def toggle_channel_quickcheck(callback: CallbackQuery):
    if callback.from_user is None or callback.message is None:
        return

    _, raw_chat_id, new_mode = callback.data.split(":", 2)
    chat_id = int(raw_chat_id)

    if new_mode not in {"manual", "auto"}:
        await callback.answer("Невідомий режим.", show_alert=True)
        return

    setting = get_channel_setting(chat_id)

    if setting is None:
        await callback.answer("Спочатку обери канал заново.", show_alert=True)
        return

    if setting["chat_type"] == "channel":
        if not await bot_can_post_to_channel(callback, chat_id):
            await callback.answer(
                "Бот більше не має права публікувати в цьому каналі.",
                show_alert=True,
            )
            return
    elif not await bot_is_chat_admin(callback, chat_id):
        await callback.answer(
            "Бот має бути адміністратором цієї групи.",
            show_alert=True,
        )
        return

    if not await user_is_chat_admin(callback, chat_id, callback.from_user.id):
        await callback.answer("Недостатньо прав адміністратора.", show_alert=True)
        return

    set_channel_mode(chat_id, new_mode, callback.from_user.id)
    status = "ввімкнено" if new_mode == "auto" else "вимкнено"

    await callback.answer(f"Автоматичну коротку перевірку {status}.")
    await callback.message.edit_text(
        f"✅ Автоматичну коротку перевірку {status}.",
        parse_mode="HTML",
    )

    command_id = PENDING_GROUP_COMMANDS.pop((chat_id, callback.from_user.id), None)

    if command_id is not None:
        try:
            await callback.bot.delete_message(chat_id=chat_id, message_id=command_id)
        except Exception:
            pass

    asyncio.create_task(delete_later(callback.message))


async def process_automatic_post(message: Message) -> None:
    text = get_post_text(message)

    if not text:
        return

    normalized = normalize_text(text)

    if is_own_marker(normalized):
        return

    setting = get_channel_setting(message.chat.id)

    if setting is None or setting["mode"] != "auto":
        return

    # Локальний фільтр лише відсіює очевидно непридатні дописи.
    # Він не визначає правдивість: остаточний вердикт формує аналіз із джерелами.
    decision = classify_channel_post(normalized)

    if not decision.eligible:
        return

    post_hash = generate_text_hash(normalized)

    if not reserve_quick_check(
        chat_id=message.chat.id,
        message_id=message.message_id,
        post_hash=post_hash,
    ):
        return

    source_type, source_title, source_link = get_post_source_info(message)
    links = extract_links(normalized)

    if source_link:
        links.append(source_link)

    links = list(dict.fromkeys(links))
    links_text = ", ".join(links) if links else None
    domains = extract_domains(links)
    domains_text = ", ".join(domains) if domains else None

    remember_content(
        content_hash=post_hash,
        original_context=normalized[:500],
        original_url=source_link or (links[0] if links else None),
    )

    cached_result = get_cached_response(normalized)

    # Re-run legacy cached checks once so new flexible verdicts can be generated.
    if cached_result is not None and not cached_result["result"].get("verdict_family"):
        cached_result = None

    if cached_result is None:
        limit_allowed, _ = check_and_use_text_limit(setting["enabled_by"])

        if not limit_allowed:
            complete_quick_check(
                chat_id=message.chat.id,
                message_id=message.message_id,
                status="skipped_no_balance",
            )
            return

    status_message = await message.bot.send_message(
        chat_id=message.chat.id,
        text=PROGRESS_FRAMES[0],
        message_thread_id=message.message_thread_id,
        disable_notification=True,
        link_preview_options=NO_LINK_PREVIEW,
    )

    async def perform_check() -> dict:
        if cached_result is not None:
            return cached_result["result"]

        result = await analyze_text(normalized)
        save_cached_response(
            text=normalized,
            response=format_fact_check_response(result),
            verdict=result.get("verdict"),
            result=result,
        )
        return result

    try:
        result = await run_with_progress(
            status_message=status_message,
            work=perform_check(),
        )
    except Exception as error:
        print(f"QUICKCHECK ERROR: {error}")
        await safe_delete_message(status_message)
        complete_quick_check(
            chat_id=message.chat.id,
            message_id=message.message_id,
            status="failed",
        )
        return

    if not result.get("public_mark_allowed", False):
        await safe_delete_message(status_message)
        complete_quick_check(
            chat_id=message.chat.id,
            message_id=message.message_id,
            status="ignored",
            verdict=result.get("verdict"),
            short_note=result.get("short_reason"),
        )
        return

    public_id = add_request(
        user_id=setting["enabled_by"],
        request_text=normalized,
        response_text=format_fact_check_response(result),
        source_type=source_type,
        source_title=source_title,
        source_link=source_link,
        detected_links=links_text,
        detected_domains=domains_text,
        verdict=result.get("verdict"),
        from_cache=cached_result is not None,
        result=result,
        is_publishable=True,
        queue_for_publication=False,
    )

    mark_text = build_quick_mark(result, public_id=public_id)

    if not mark_text:
        await safe_delete_message(status_message)
        complete_quick_check(
            chat_id=message.chat.id,
            message_id=message.message_id,
            status="ignored",
            verdict=result.get("verdict"),
            short_note=result.get("short_reason"),
        )
        return

    marker_updated = await safe_edit_message(
        status_message,
        mark_text,
        parse_mode="HTML",
        link_preview_options=NO_LINK_PREVIEW,
    )

    complete_quick_check(
        chat_id=message.chat.id,
        message_id=message.message_id,
        status="published" if marker_updated else "failed_marker_edit",
        verdict=result.get("verdict"),
        short_note=result.get("short_reason"),
        marker_message_id=status_message.message_id if marker_updated else None,
        public_id=public_id,
        was_reply=False,
    )


@router.channel_post()
async def auto_channel_post_handler(message: Message):
    await process_automatic_post(message)


@router.message(F.chat.type.in_({"group", "supergroup"}), ~F.text.startswith("/"))
async def auto_group_message_handler(message: Message):
    if message.from_user is not None and message.from_user.is_bot:
        return

    await process_automatic_post(message)
