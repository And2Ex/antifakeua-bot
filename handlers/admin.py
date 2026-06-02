from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database.db import (
    admin_add_paid_balance,
    approve_donation_and_add_balance,
    approve_latest_pending_donation_for_user,
    get_default_free_limit,
    get_donation_stats,
    get_donation_submission,
    get_recent_donation_submissions,
    is_admin_notifications_enabled,
    get_basic_stats,
    get_chat_source_stats,
    get_domain_stats,
    get_payment_debug,
    get_payment_stats,
    get_recent_feedback,
    get_recent_payments,
    get_user,
    remove_user_custom_free_limit,
    reset_all_limits,
    reset_user_limits,
    set_admin_notifications_enabled,
    set_default_free_limit,
    set_user_text_limit,
)
from keyboards.admin import (
    ADMIN_BACK_KEYBOARD,
    build_admin_notifications_keyboard,
    build_default_free_limit_keyboard,
    get_admin_keyboard,
)


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

    donation_stats = get_donation_stats()
    donation_lines = [
        f"{row['status']}: {row['count']}"
        for row in donation_stats["status_stats"]
    ]

    quick_check_lines = [
        f"{row['status']}: {row['count']}"
        for row in stats["quick_check_status_stats"]
    ]

    verdict_text = "\n".join(verdict_lines) if verdict_lines else "ще немає даних"
    publication_text = "\n".join(publication_lines) if publication_lines else "ще немає даних"
    donation_text = "\n".join(donation_lines) if donation_lines else "ще немає даних"
    quick_check_text = "\n".join(quick_check_lines) if quick_check_lines else "ще немає даних"

    await message.answer(
        "📊 <b>Статистика бота</b>\n\n"
        f"Користувачів: {stats['users_count']}\n"
        f"Запитів: {stats['requests_count']}\n"
        f"Кешованих відповідей: {stats['cache_count']}\n"
        f"Відгуків: {stats['feedback_count']}\n"
        f"Заявок підтримки: {donation_stats['submissions_count']}\n"
        f"Каналів з авто-QuickCheck: {stats['automatic_channels_count']}\n"
        f"Коротких перевірок: {stats['quick_checks_count']}\n\n"
        "<b>Вердикти:</b>\n"
        f"{escape(verdict_text)}\n\n"
        "<b>Публікації:</b>\n"
        f"{escape(publication_text)}\n\n"
        "<b>QuickCheck:</b>\n"
        f"{escape(quick_check_text)}\n\n"
        "<b>Підтримка:</b>\n"
        f"{escape(donation_text)}",
        parse_mode="HTML",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )


async def send_donation_stats(message: Message) -> None:
    stats = get_donation_stats()
    submissions = get_recent_donation_submissions(limit=10)
    status_lines = [
        f"{row['status']}: {row['count']}"
        for row in stats["status_stats"]
    ]
    parts = [
        "💙 <b>Підтримка й додаткові ліміти</b>",
        "",
        f"Усього скріншотів: {stats['submissions_count']}",
        f"Надано додаткових перевірок: {stats['checks_total']}",
        "",
        "<b>Статуси:</b>",
        escape("\n".join(status_lines) if status_lines else "ще немає даних"),
    ]

    if submissions:
        parts.extend(["", "<b>Останні заявки:</b>"])

        for item in submissions:
            parts.append(
                f"#{item['id']} · user_id=<code>{item['user_id']}</code> · "
                f"{escape(item['status'])} · +{item['checks_added'] or 0}"
            )

    await message.answer(
        "\n".join(parts),
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


async def send_notifications_settings(message: Message) -> None:
    enabled = is_admin_notifications_enabled()
    status = "увімкнені" if enabled else "вимкнені"

    await message.answer(
        "🔔 <b>Адмін-сповіщення</b>\n\n"
        f"Поточний стан: <b>{status}</b>.\n\n"
        "Коли сповіщення увімкнені, бот надсилатиме тобі повідомлення про:\n"
        "• нових користувачів;\n"
        "• додавання бота в групи;\n"
        "• нові перевірки;\n"
        "• заявки підтримки й надання додаткових лімітів.\n\n"
        "Якщо користувачів стане багато, їх можна вимкнути цією кнопкою.",
        parse_mode="HTML",
        reply_markup=build_admin_notifications_keyboard(enabled),
    )


async def send_default_free_limit_settings(message: Message) -> None:
    current_limit = get_default_free_limit()

    await message.answer(
        "⚙️ <b>Стандартний безкоштовний ліміт</b>\n\n"
        f"Поточне значення: <b>{current_limit} перевірок на місяць</b>.\n\n"
        "Після зміни:\n"
        "• нові користувачі одразу отримають новий ліміт;\n"
        "• для наявних користувачів він застосовується під час наступного місячного оновлення;\n"
        "• уже доступні в поточному періоді перевірки не забираються;\n"
        "• додатковий баланс за підтримку не змінюється;\n"
        "• персональні free-ліміти, встановлені командою <code>/setlimit</code>, залишаються окремими.\n\n"
        "Інше значення можна встановити командою <code>/setdefaultlimit ЧИСЛО</code>.",
        parse_mode="HTML",
        reply_markup=build_default_free_limit_keyboard(current_limit),
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

    await callback.answer()
    await callback.message.answer(
        "🛠 <b>Адмін-панель</b>",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard(),
    )


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

    await callback.answer()
    await send_stats(callback.message)


@router.message(Command("donations"))
async def donation_stats_handler(message: Message):
    if not await require_admin_message(message):
        return

    await send_donation_stats(message)


@router.callback_query(F.data == "admin:donations")
async def donation_stats_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.answer()
    await send_donation_stats(callback.message)


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

    await callback.answer()
    await send_source_stats(callback.message)


@router.callback_query(F.data == "admin:feedback")
async def recent_feedback_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.answer()
    await send_recent_feedback(callback.message)


@router.callback_query(F.data == "admin:notifications")
async def admin_notifications_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.answer()
    await send_notifications_settings(callback.message)


@router.callback_query(F.data == "admin:notifications_toggle")
async def admin_notifications_toggle_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    current = is_admin_notifications_enabled()
    set_admin_notifications_enabled(not current)

    await callback.answer("Сповіщення оновлено")
    await send_notifications_settings(callback.message)


@router.callback_query(F.data == "admin:default_free_limit")
async def default_free_limit_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.answer()
    await send_default_free_limit_settings(callback.message)


@router.callback_query(F.data.startswith("admin:default_free_limit:set:"))
async def set_default_free_limit_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    try:
        limit = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer("Некоректний ліміт.", show_alert=True)
        return

    if not set_default_free_limit(limit):
        await callback.answer("Ліміт не може бути від’ємним.", show_alert=True)
        return

    await callback.answer(f"Новий стандарт: {limit}")
    await send_default_free_limit_settings(callback.message)


@router.callback_query(F.data == "admin:review")
async def review_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.answer()
    from handlers.review import send_review_queue

    await send_review_queue(callback.message)


@router.callback_query(F.data == "admin:reset_limits")
async def reset_limits_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.answer("Скидаю…")
    reset_all_limits()
    await callback.message.answer(
        "♻️ Безкоштовні ліміти всіх користувачів скинуто. Платний баланс не змінено.",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )


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
    await message.answer(f"Ліміт користувача {user_id} скинуто разом із додатковим балансом.")


@router.message(Command("setdefaultlimit"))
async def set_default_limit_handler(message: Message):
    if not await require_admin_message(message):
        return

    parts = message.text.split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            "Неправильний формат.\n\n"
            "Приклад:\n"
            "/setdefaultlimit 3"
        )
        return

    limit = int(parts[1])

    if not set_default_free_limit(limit):
        await message.answer("Ліміт не може бути від’ємним.")
        return

    await message.answer(
        f"Новий стандартний free-ліміт: {limit} перевірок на місяць.\n\n"
        "Нові користувачі отримають його одразу, а наявні стандартні користувачі — "
        "під час наступного місячного оновлення. Додатковий баланс не змінено."
    )


@router.message(Command("usedefaultlimit"))
async def use_default_limit_handler(message: Message):
    if not await require_admin_message(message):
        return

    parts = message.text.split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            "Неправильний формат.\n\n"
            "Приклад:\n"
            "/usedefaultlimit 486192692"
        )
        return

    user_id = int(parts[1])

    if not remove_user_custom_free_limit(user_id):
        await message.answer("Користувача не знайдено.")
        return

    await message.answer(
        f"Персональний free-ліміт користувача {user_id} вимкнено. "
        "Із наступного щомісячного оновлення застосовуватиметься загальний стандарт."
    )


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
    await message.answer(f"Користувачу {user_id} встановлено персональний free-ліміт: {texts_limit}")


@router.message(Command("paymentsrecent"))
async def recent_payments_handler(message: Message):
    if not await require_admin_message(message):
        return

    await send_recent_payments(message)


@router.callback_query(F.data == "admin:payments_recent")
async def recent_payments_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.answer()
    await send_recent_payments(callback.message)


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
@router.message(Command("grant"))
async def add_balance_handler(message: Message):
    if not await require_admin_message(message):
        return

    parts = message.text.split()

    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer(
            "Неправильний формат.\n\n"
            "Приклад:\n"
            "/grant 486192692 100"
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

    approve_latest_pending_donation_for_user(
        user_id=user_id,
        reviewed_by=message.from_user.id,
        checks_added=checks,
    )

    await message.answer(f"Користувачу {user_id} додано {checks} додаткових перевірок.")

    try:
        await message.bot.send_message(
            chat_id=user_id,
            text=(
                "💙 <b>Дякуємо за підтримку AntiFakeUA</b>\n\n"
                f"Вам надано додатковий ліміт: <b>{checks} перевірок</b>.\n\n"
                "Поточний баланс можна переглянути командою <code>/limits</code>."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("donation:grant:"))
async def donation_grant_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    try:
        _, _, raw_submission_id, raw_checks = callback.data.split(":", 3)
        submission_id = int(raw_submission_id)
        checks = int(raw_checks)
    except (ValueError, AttributeError):
        await callback.answer("Некоректна заявка.", show_alert=True)
        return

    submission = approve_donation_and_add_balance(
        submission_id=submission_id,
        reviewed_by=callback.from_user.id,
        checks_added=checks,
    )

    if submission is None:
        await callback.answer("Заявку вже оброблено або не знайдено.", show_alert=True)
        return

    await callback.answer("Додатковий ліміт надано.")
    await callback.message.edit_caption(
        caption=(
            "✅ <b>Підтримку підтверджено</b>\n\n"
            f"Користувач: <code>{submission['user_id']}</code>\n"
            f"Надано: <b>+{checks} перевірок</b>"
        ),
        parse_mode="HTML",
    )

    try:
        await callback.bot.send_message(
            chat_id=submission["user_id"],
            text=(
                "💙 <b>Дякуємо за підтримку AntiFakeUA</b>\n\n"
                f"Вам надано додатковий ліміт: <b>{checks} перевірок</b>.\n\n"
                "Поточний баланс можна переглянути командою <code>/limits</code>."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("donation:reject:"))
async def donation_reject_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    try:
        submission_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer("Некоректна заявка.", show_alert=True)
        return

    submission = get_donation_submission(submission_id)

    if submission is None or not update_donation_submission(
        submission_id=submission_id,
        status="rejected",
        reviewed_by=callback.from_user.id,
    ):
        await callback.answer("Заявку вже оброблено або не знайдено.", show_alert=True)
        return

    await callback.answer("Заявку відхилено.")
    await callback.message.edit_caption(
        caption=(
            "❌ <b>Скріншот не підтверджено</b>\n\n"
            f"Користувач: <code>{submission['user_id']}</code>"
        ),
        parse_mode="HTML",
    )

    try:
        await callback.bot.send_message(
            chat_id=submission["user_id"],
            text=(
                "Не вдалося підтвердити скріншот підтримки. "
                "Надішліть коректний скріншот переказу через <code>/support</code> "
                "або зверніться через розділ відгуку."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass


@router.callback_query(F.data == "admin:commands")
async def admin_commands_callback(callback: CallbackQuery):
    if not await require_admin_callback(callback):
        return

    await callback.answer()
    await callback.message.answer(
        "🧰 <b>Технічні адмін-команди</b>\n\n"
        "Вони не показуються в меню Telegram, але працюють вручну:\n\n"
        "<code>/grant USER_ID 100</code> — надати додатковий ліміт після підтримки\n"
        "<code>/setdefaultlimit 3</code> — змінити стандартний місячний free-ліміт\n"
        "<code>/setlimit USER_ID 100</code> — встановити персональний free-ліміт\n"
        "<code>/usedefaultlimit USER_ID</code> — повернути користувача до загального стандарту з наступного оновлення\n"
        "<code>/resetlimits USER_ID</code> — скинути ліміти користувача\n"
        "<code>/publish check_xxxxx</code> — сформувати чернетку публікації за ID\n"
        "<code>/prompt</code> — показати prompt",
        parse_mode="HTML",
        reply_markup=ADMIN_BACK_KEYBOARD,
    )
