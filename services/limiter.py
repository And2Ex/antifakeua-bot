from database.db import get_user, reset_monthly_free_limit_if_needed, use_text_quota


def check_and_use_text_limit(user_id: int) -> tuple[bool, str]:
    return use_text_quota(user_id)


def get_limit_info(user_id: int) -> str:
    reset_monthly_free_limit_if_needed(user_id)
    user = get_user(user_id)

    if user is None:
        return "Користувача не знайдено. Натисни /start."

    return (
        "Твої ліміти:\n\n"
        f"Тариф: {user['plan']}\n"
        f"Безкоштовні перевірки цього місяця: {user['free_used']}/{user['free_limit']}\n"
        f"Платний баланс: {user['paid_balance']}\n\n"
        "Безкоштовні перевірки автоматично оновлюються 1 числа кожного місяця. "
        "Куплені перевірки додаються до платного балансу й не згорають при щомісячному оновленні free-ліміту."
    )
