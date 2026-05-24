from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database.db import (
    admin_add_paid_balance,
    get_basic_stats,
    get_chat_source_stats,
    get_domain_stats,
    get_payment_debug,
    get_payment_stats,
    get_recent_feedback,
    get_recent_payments,
    get_user,
    reset_all_limits,
    reset_user_limits,
    set_user_text_limit,
)
from keyboards.admin import ADMIN_BACK_KEYBOARD, get_admin_keyboard


router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def require_admin_message(message: Message) -> bool:
    if is_admin(message.from_user.id):
        return True

    await message.answer("Ця дія доступна лише адміністратору.")
    return False


async def require_admin_callback(callback: CallbackQuery) -> bool:
    if is_admin(callback.from_user.id):
        return True

    await callback.answer("Недостатньо прав.", show_alert=True)
    return False


async def send_admin_menu(message: Message) -> None:
    await message.answer(
        "🛠 <b>Адмін-панель</b>\n\n"
        "Основні дії винесені в кнопки. Технічні команди з аргументами залишені прихованими, "
        "щоб не засмічувати меню Telegram.",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(),
    )


async def send_stats(message: Message) -> None:
    stats = get_basic_stats()

    verdict_lines = [
        f"{row['verdict']}: {row['count']}"
        for row in stats["verdict_stats"]
    ]

    publication_lines = [
        f"{row['publication_status']}: {row['count']}"
        for row in stats["publication_stats"]
    ]

    payment_lines = [
        f"{row['status']}: {row['count']}"
        for row in stats["payment_status_stats"]
    ]

    verdict_text = "\n".join(verdict_lines) if verdict_lines else "ще немає даних"
    publication_text = "\n".join(publication_lines) if publication_lines else "ще немає даних"
    payment_text = "\n".join(payment_lines) if payment_lines else "ще немає даних"

    await message.answer(
        "📊 <b>Статистика бота</b>\n\n"
        f"Користувачів: {stats['users_count']}\n"
        f"Запитів: {stats['requests_count']}\n"
        f"Кешованих відповідей: {stats['cache_count']}\n"
        f"Відгуків: {stats['feedback_count']}\n"
        f"Платежів: {stats['payments_count']}\n\n"
        "<b>Вердикти:</b>\n"
        f"{escape(verdict_text)}\n\n"
        "<b>Публікації:</b>\n"
        f"{escape(publication_text)}\n\n"
        "<b>Платежі:</b>\n"
        f"{escape(payment_text)}",
        parse_mode="HTML",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )


async def send_payment_stats(message: Message) -> None:
    stats = get_payment_stats()

    status_lines = [
        f"{row['status']}: {row['count']}"
        for row in stats["status_stats"]
    ]

    status_text = "\n".join(status_lines) if status_lines else "ще немає даних"

    await message.answer(
        "💳 <b>Статистика оплат</b>\n\n"
        f"Усього платежів: {stats['payments_count']}\n"
        f"Оплачених перевірок: {stats['paid_checks_total']}\n"
        f"Сума успішних оплат: {stats['paid_amount_total']:.2f} UAH\n\n"
        "<b>Статуси:</b>\n"
        f"{escape(status_text)}",
        parse_mode="HTML",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )


async def send_source_stats(message: Message) -> None:
    domain_stats = get_domain_stats()
    chat_stats = get_chat_source_stats()

    parts = ["🌐 <b>Статистика джерел</b>", ""]

    if domain_stats:
        parts.append("<b>Домени:</b>")

        for domain, verdicts in list(domain_stats.items())[:15]:
            verdict_text = ", ".join(
                f"{verdict}: {count}"
                for verdict, count in verdicts.items()
            )
            parts.append(f"• {escape(domain)} — {escape(verdict_text)}")
    else:
        parts.append("Домени: ще немає даних.")

    parts.append("")

    if chat_stats:
        parts.append("<b>Telegram-чати/канали:</b>")

        for row in chat_stats[:15]:
            parts.append(
                f"• {escape(row['source_title'])} — "
                f"{escape(row['verdict'])}: {row['count']}"
            )
    else:
        parts.append("Telegram-чати/канали: ще немає даних.")

    await message.answer(
        "\n".join(parts),
        parse_mode="HTML",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )


async def send_recent_payments(message: Message) -> None:
    payments = get_recent_payments(limit=10)

    if not payments:
        await message.answer(
            "Платежів ще немає.",
            reply_markup=ADMIN_BACK_KEYBOARD,
        )
        return

    lines = ["🧾 <b>Останні платежі</b>", ""]

    for payment in payments:
        lines.append(
            f"#{payment['id']} {escape(payment['status'])} | "
            f"user_id={payment['user_id']} | "
            f"{escape(payment['package_title'])} | "
            f"+{payment['checks_added']} | "
            f"{payment['amount']:.2f} {escape(payment['currency'])}\n"
            f"order_id: <code>{escape(payment['order_id'])}</code>\n"
        )

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )


async def send_recent_feedback(message: Message) -> None:
    feedback_items = get_recent_feedback(limit=10)

    if not feedback_items:
        await message.answer(
            "Відгуків ще немає.",
            reply_markup=ADMIN_BACK_KEYBOARD,
        )
        return

    lines = ["✉️ <b>Останні відгуки</b>", ""]

    for item in feedback_items:
        username = item["username"] or "без username"
        feedback_text = item["feedback_text"] or ""

        if len(feedback_text) > 500:
            feedback_text = feedback_text[:500] + "..."

        lines.append(
            f"#{item['id']} | user_id={item['user_id']} | @{escape(username)}\n"
            f"{escape(feedback_text)}\n"
            f"<i>{escape(str(item['created_at']))}</i>\n"
        )

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )


@router.message(Command("admin"))
async def admin_handler(message: Message):
    if not await require_admin_message(message):
        return

    await send_admin_menu(message)


@router.callback_query(F.data == "admin:menu")
async def admin_menu_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.message.answer(
        "🛠 <b>Адмін-панель</b>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(),
    )
    await callback.answer()


@router.message(Command("stats"))
@router.message(F.text == "📊 Статистика")
async def stats_handler(message: Message):
    if not await require_admin_message(message):
        return

    await send_stats(message)


@router.callback_query(F.data == "admin:stats")
async def stats_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await send_stats(callback.message)
    await callback.answer()


@router.message(Command("paymentstats"))
async def payment_stats_handler(message: Message):
    if not await require_admin_message(message):
        return

    await send_payment_stats(message)


@router.callback_query(F.data == "admin:payments")
async def payment_stats_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await send_payment_stats(callback.message)
    await callback.answer()


@router.message(Command("sourcestats"))
@router.message(F.text == "🌐 Статистика джерел")
async def source_stats_handler(message: Message):
    if not await require_admin_message(message):
        return

    await send_source_stats(message)


@router.callback_query(F.data == "admin:sources")
async def source_stats_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await send_source_stats(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin:feedback")
async def recent_feedback_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await send_recent_feedback(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin:review")
async def review_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    from handlers.review import send_next_review

    await send_next_review(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin:reset_limits")
async def reset_limits_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    reset_all_limits()
    await callback.message.answer(
        "♻️ Безкоштовні ліміти всіх користувачів скинуто. Платний баланс не змінено.",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )
    await callback.answer("Скинуто.")


@router.message(F.text == "♻️ Скинути ліміти")
async def reset_limits_button_handler(message: Message):
    if not await require_admin_message(message):
        return

    reset_all_limits()
    await message.answer("Безкоштовні ліміти всіх користувачів скинуто. Платний баланс не змінено.")


@router.message(Command("resetlimits"))
async def reset_limits_handler(message: Message):
    if not await require_admin_message(message):
        return

    parts = message.text.split()

    if len(parts) == 1:
        reset_all_limits()
        await message.answer("Безкоштовні ліміти всіх користувачів скинуто. Платний баланс не змінено.")
        return

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            "Неправильний формат.\n\n"
            "Приклад:\n"
            "/resetlimits 486192692"
        )
        return

    user_id = int(parts[1])
    user = get_user(user_id)

    if user is None:
        await message.answer("Користувача не знайдено.")
        return

    reset_user_limits(user_id)
    await message.answer(f"Ліміт користувача {user_id} скинуто разом із платним балансом.")


@router.message(Command("setlimit"))
async def set_limit_handler(message: Message):
    if not await require_admin_message(message):
        return

    parts = message.text.split()

    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer(
            "Неправильний формат.\n\n"
            "Приклад:\n"
            "/setlimit 486192692 100"
        )
        return

    user_id = int(parts[1])
    texts_limit = int(parts[2])
    user = get_user(user_id)

    if user is None:
        await message.answer("Користувача не знайдено.")
        return

    set_user_text_limit(user_id=user_id, texts_limit=texts_limit)
    await message.answer(f"Користувачу {user_id} встановлено free-ліміт: {texts_limit}")


@router.message(Command("paymentsrecent"))
async def recent_payments_handler(message: Message):
    if not await require_admin_message(message):
        return

    await send_recent_payments(message)


@router.callback_query(F.data == "admin:payments_recent")
async def recent_payments_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await send_recent_payments(callback.message)
    await callback.answer()


@router.message(Command("paymentdebug"))
async def payment_debug_handler(message: Message):
    if not await require_admin_message(message):
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "Неправильний формат.\n\n"
            "Приклад:\n"
            "/paymentdebug afua_123_basic_..."
        )
        return

    order_id = parts[1].strip()
    payment, user = get_payment_debug(order_id)

    if payment is None:
        await message.answer("Платіж з таким order_id не знайдено.")
        return

    raw_data = payment["raw_data"] or "немає"

    if len(raw_data) > 1200:
        raw_data = raw_data[:1200] + "..."

    user_text = "користувача не знайдено"

    if user is not None:
        user_text = (
            f"plan={user['plan']}, "
            f"free={user['free_used']}/{user['free_limit']}, "
            f"paid_balance={user['paid_balance']}"
        )

    await message.answer(
        "Дані платежу:\n\n"
        f"order_id: {payment['order_id']}\n"
        f"status: {payment['status']}\n"
        f"user_id: {payment['user_id']}\n"
        f"package: {payment['package_title']}\n"
        f"checks_added: {payment['checks_added']}\n"
        f"amount: {payment['amount']:.2f} {payment['currency']}\n"
        f"created_at: {payment['created_at']}\n"
        f"updated_at: {payment['updated_at']}\n"
        f"paid_at: {payment['paid_at']}\n\n"
        f"Користувач: {user_text}\n\n"
        f"raw_data:\n{raw_data}"
    )


@router.message(Command("addbalance"))
async def add_balance_handler(message: Message):
    if not await require_admin_message(message):
        return

    parts = message.text.split()

    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer(
            "Неправильний формат.\n\n"
            "Приклад:\n"
            "/addbalance 486192692 100"
        )
        return

    user_id = int(parts[1])
    checks = int(parts[2])

    if checks <= 0:
        await message.answer("Кількість перевірок має бути більшою за 0.")
        return

    changed = admin_add_paid_balance(user_id=user_id, checks=checks)

    if not changed:
        await message.answer("Не вдалося додати баланс.")
        return

    await message.answer(f"Користувачу {user_id} додано {checks} платних перевірок.")


@router.callback_query(F.data == "admin:commands")
async def admin_commands_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.message.answer(
        "🧰 <b>Технічні адмін-команди</b>\n\n"
        "Вони не показуються в меню Telegram, але працюють вручну:\n\n"
        "<code>/paymentdebug ORDER_ID</code> — діагностика платежу\n"
        "<code>/addbalance USER_ID 100</code> — додати баланс\n"
        "<code>/setlimit USER_ID 100</code> — встановити free-ліміт\n"
        "<code>/resetlimits USER_ID</code> — скинути ліміти користувача\n"
        "<code>/publish check_xxxxx</code> — опублікувати перевірку за ID\n"
        "<code>/prompt</code> — показати prompt",
        parse_mode="HTML",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )
    await callback.answer()
