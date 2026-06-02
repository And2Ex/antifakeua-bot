from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import (
    ADMIN_IDS,
    PACKAGE_BASIC_CHECKS,
    PACKAGE_BASIC_PRICE_UAH,
    PACKAGE_PRO_CHECKS,
    PACKAGE_PRO_PRICE_UAH,
)
from database.db import is_admin_notifications_enabled


def format_user_label(user_id: int | None, username: str | None = None, first_name: str | None = None) -> str:
    parts = []

    if first_name:
        parts.append(escape(first_name))

    if username:
        parts.append(f"@{escape(username)}")

    if user_id is not None:
        parts.append(f"<code>{user_id}</code>")

    return " | ".join(parts) if parts else "невідомий користувач"


async def notify_admins(
    bot: Bot,
    title: str,
    lines: list[str],
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if not ADMIN_IDS or not is_admin_notifications_enabled():
        return

    text = "\n".join([f"<b>{escape(title)}</b>", "", *lines]).strip()

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
                disable_notification=True,
            )
        except Exception as error:
            print(f"ADMIN NOTIFY ERROR for {admin_id}: {error}")


async def notify_new_user(bot: Bot, user_id: int, username: str | None, first_name: str | None) -> None:
    await notify_admins(
        bot,
        "Новий користувач AntiFakeUA",
        [
            f"Користувач: {format_user_label(user_id, username, first_name)}",
            "Він уперше відкрив бота або зробив першу дію.",
        ],
    )


async def notify_new_group(bot: Bot, chat_id: int, title: str | None, chat_type: str | None) -> None:
    await notify_admins(
        bot,
        "Бота додано в канал або групу",
        [
            f"Назва: <b>{escape(title or 'без назви')}</b>",
            f"Тип: {escape(chat_type or 'невідомо')}",
            f"Chat ID: <code>{chat_id}</code>",
        ],
    )


async def notify_check_completed(
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    verdict: str | None,
    source_title: str | None,
    from_cache: bool,
    text: str,
    public_id: str | None = None,
    is_publishable: bool = False,
) -> None:
    snippet = text.strip().replace("\n", " ")

    if len(snippet) > 350:
        snippet = snippet[:350] + "..."

    keyboard = None

    if is_publishable and public_id:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📰 Публікація",
                        callback_data=f"review_open:{public_id}",
                    )
                ]
            ]
        )

    await notify_admins(
        bot,
        "Нова перевірка",
        [
            f"Користувач: {format_user_label(user_id, username, first_name)}",
            f"Вердикт: <b>{escape(verdict or 'не визначено')}</b>",
            f"Джерело: {escape(source_title or 'не вказано')}",
            f"Кеш: {'так' if from_cache else 'ні'}",
            "",
            f"<i>{escape(snippet)}</i>",
        ],
        reply_markup=keyboard,
    )


async def notify_donation_screenshot(
    bot: Bot,
    *,
    submission_id: int,
    user_id: int,
    username: str | None,
    first_name: str | None,
    photo_file_id: str,
) -> None:
    if not ADMIN_IDS:
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"+{PACKAGE_BASIC_CHECKS} ({PACKAGE_BASIC_PRICE_UAH} грн)",
                    callback_data=f"donation:grant:{submission_id}:{PACKAGE_BASIC_CHECKS}",
                ),
                InlineKeyboardButton(
                    text=f"+{PACKAGE_PRO_CHECKS} ({PACKAGE_PRO_PRICE_UAH} грн)",
                    callback_data=f"donation:grant:{submission_id}:{PACKAGE_PRO_CHECKS}",
                ),
            ],
            [
                InlineKeyboardButton(text="Відхилити", callback_data=f"donation:reject:{submission_id}"),
            ],
        ]
    )
    caption = (
        "💙 <b>Новий скріншот підтримки</b>\n\n"
        f"Користувач: {format_user_label(user_id, username, first_name)}\n"
        f"Заявка: <code>#{submission_id}</code>\n\n"
        "Звір суму на скріншоті та активуй відповідний пакет або використай команду:\n"
        f"<code>/grant {user_id} {PACKAGE_BASIC_CHECKS}</code>"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo_file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_notification=False,
            )
        except Exception as error:
            print(f"DONATION NOTIFY ERROR for {admin_id}: {error}")
