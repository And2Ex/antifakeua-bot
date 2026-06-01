from config import (
    PACKAGE_BASIC_CHECKS,
    PACKAGE_BASIC_PRICE_UAH,
    PACKAGE_PRO_CHECKS,
    PACKAGE_PRO_PRICE_UAH,
)
from database.db import get_user, reset_monthly_free_limit_if_needed, use_text_quota


def check_and_use_text_limit(user_id: int) -> tuple[bool, str]:
    return use_text_quota(user_id)


def get_limit_info(user_id: int) -> str:
    reset_monthly_free_limit_if_needed(user_id)
    user = get_user(user_id)

    if user is None:
        return "<b>Користувача не знайдено</b>\n\nНатисни <code>/start</code>, щоб створити профіль у боті."

    free_remaining = max(user["free_limit"] - user["free_used"], 0)

    return (
        "<b>Мої ліміти</b>\n\n"
        f"<b>Безкоштовні перевірки:</b> {free_remaining} із {user['free_limit']}\n"
        f"<b>Додатковий ліміт:</b> {user['paid_balance']}\n\n"
        "Безкоштовний ліміт оновлюється щомісяця. Додаткові перевірки не згорають після його оновлення.\n\n"
        "<b>Пакети додаткових перевірок</b>\n"
        f"• +{PACKAGE_BASIC_CHECKS} перевірок — <b>{PACKAGE_BASIC_PRICE_UAH} грн</b>\n"
        f"• +{PACKAGE_PRO_CHECKS} перевірок — <b>{PACKAGE_PRO_PRICE_UAH} грн</b>\n\n"
        "Щоб отримати пакет, відкрий <b>«💙 Підтримати»</b>, зроби переказ на суму обраного пакета "
        "і саме в цьому розділі надішли скріншот оплати."
    )
