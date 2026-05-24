from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="ℹ️ Про бота і як користуватись", callback_data="menu:about"),
        ],
        [
            InlineKeyboardButton(text="🔗 Посилання і відкритість", callback_data="menu:transparency"),
        ],
        [
            InlineKeyboardButton(text="📊 Мої ліміти", callback_data="menu:limits"),
            InlineKeyboardButton(text="💳 Купити перевірки", callback_data="buy_menu"),
        ],
        [
            InlineKeyboardButton(text="🌐 Репутація джерела", callback_data="menu:source"),
            InlineKeyboardButton(text="✉️ Відгук", callback_data="menu:feedback"),
        ],
    ]

    if is_admin:
        rows.append([
            InlineKeyboardButton(text="🛠 Адмін-панель", callback_data="admin:menu"),
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


BACK_TO_MENU_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ До меню", callback_data="menu:main")],
    ]
)


FEEDBACK_MENU_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Написати відгук", callback_data="feedback:start")],
        [InlineKeyboardButton(text="⬅️ До меню", callback_data="menu:main")],
    ]
)


TRANSPARENCY_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📄 Показати prompt", callback_data="menu:prompt")],
        [InlineKeyboardButton(text="⬅️ До меню", callback_data="menu:main")],
    ]
)
