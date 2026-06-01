from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import SUPPORT_JAR_URL


SUPPORT_ENTRY_KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💙 Підтримати AntiFakeUA", callback_data="support:open")],
    ]
)


def build_support_keyboard() -> InlineKeyboardMarkup:
    rows = []

    if SUPPORT_JAR_URL:
        rows.append([
            InlineKeyboardButton(text="💙 Відкрити банку Monobank", url=SUPPORT_JAR_URL),
        ])

    rows.append([
        InlineKeyboardButton(text="⬅️ До меню", callback_data="menu:main"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)
