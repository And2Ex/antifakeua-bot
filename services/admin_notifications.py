from html import escape

from aiogram import Bot

from config import ADMIN_IDS
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


async def notify_admins(bot: Bot, title: str, lines: list[str]) -> None:
    if not ADMIN_IDS or not is_admin_notifications_enabled():
        return

    text = "\n".join([f"<b>{escape(title)}</b>", "", *lines]).strip()

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML",
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
) -> None:
    snippet = text.strip().replace("\n", " ")

    if len(snippet) > 350:
        snippet = snippet[:350] + "..."

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
    )


async def notify_payment_credited(
    bot: Bot,
    *,
    user_id: int,
    package_title: str,
    checks_added: int,
    sandbox: bool,
) -> None:
    await notify_admins(
        bot,
        "Активовано пакет перевірок",
        [
            f"Користувач: <code>{user_id}</code>",
            f"Пакет: <b>{escape(package_title)}</b>",
            f"Додано перевірок: <b>{checks_added}</b>",
            f"Режим: {'sandbox' if sandbox else 'бойова оплата'}",
        ],
    )
