from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


ADMIN_PANEL_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats"),
            InlineKeyboardButton(text="🌐 Джерела", callback_data="admin:sources"),
        ],
        [
            InlineKeyboardButton(text="💳 Оплати", callback_data="admin:payments"),
            InlineKeyboardButton(text="🧾 Останні платежі", callback_data="admin:payments_recent"),
        ],
        [
            InlineKeyboardButton(text="✉️ Відгуки", callback_data="admin:feedback"),
            InlineKeyboardButton(text="🔔 Сповіщення", callback_data="admin:notifications"),
        ],
        [
            InlineKeyboardButton(text="🧾 Черга публікацій", callback_data="admin:review"),
            InlineKeyboardButton(text="♻️ Скинути free-ліміти", callback_data="admin:reset_limits"),
        ],
        [
            InlineKeyboardButton(text="🧰 Технічні команди", callback_data="admin:commands"),
        ],
    ]
)


ADMIN_BACK_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ До адмін-панелі", callback_data="admin:menu")],
    ]
)


def build_admin_notifications_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    button_text = "🔕 Вимкнути сповіщення" if enabled else "🔔 Увімкнути сповіщення"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=button_text, callback_data="admin:notifications_toggle")],
            [InlineKeyboardButton(text="⬅️ До адмін-панелі", callback_data="admin:menu")],
        ]
    )


def get_admin_keyboard() -> InlineKeyboardMarkup:
    return ADMIN_PANEL_KEYBOARD
