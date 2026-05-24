from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import ADMIN_IDS
from database.db import add_feedback
from keyboards.menu import BACK_TO_MENU_KEYBOARD


router = Router()

PENDING_FEEDBACK_USERS: set[int] = set()


def is_waiting_for_feedback(message: Message) -> bool:
    return (
        message.from_user is not None
        and message.from_user.id in PENDING_FEEDBACK_USERS
    )


def save_feedback(message: Message, feedback_text: str) -> None:
    add_feedback(
        user_id=message.from_user.id,
        username=message.from_user.username,
        feedback_text=feedback_text,
    )


async def notify_admins_about_feedback(message: Message, feedback_text: str) -> None:
    if not ADMIN_IDS:
        return

    username = message.from_user.username
    user_label = f"@{username}" if username else "без username"

    text = (
        "✉️ <b>Новий відгук</b>\n\n"
        f"<b>Користувач:</b> {escape(user_label)}\n"
        f"<b>User ID:</b> <code>{message.from_user.id}</code>\n\n"
        f"{escape(feedback_text)}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(admin_id, text, parse_mode="HTML")
        except Exception:
            pass


@router.callback_query(F.data == "feedback:start")
async def feedback_start_callback(callback: CallbackQuery):
    PENDING_FEEDBACK_USERS.add(callback.from_user.id)

    await callback.message.answer(
        "✉️ Напиши відгук одним повідомленням.\n\n"
        "Щоб скасувати, напиши /cancel.",
        reply_markup=BACK_TO_MENU_KEYBOARD,
    )
    await callback.answer()


@router.message(Command("cancel"))
async def cancel_feedback_handler(message: Message):
    if message.from_user.id not in PENDING_FEEDBACK_USERS:
        return

    PENDING_FEEDBACK_USERS.discard(message.from_user.id)
    await message.answer("Надсилання відгуку скасовано.")


@router.message(Command("feedback"))
async def feedback_handler(message: Message):
    feedback_text = message.text.replace("/feedback", "", 1).strip()

    if not feedback_text:
        PENDING_FEEDBACK_USERS.add(message.from_user.id)
        await message.answer(
            "✉️ Напиши відгук наступним повідомленням.\n\n"
            "Щоб скасувати, напиши /cancel."
        )
        return

    save_feedback(message, feedback_text)
    await notify_admins_about_feedback(message, feedback_text)
    await message.answer("Дякую. Відгук збережено.")


@router.message(is_waiting_for_feedback, F.text)
async def feedback_text_handler(message: Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if not text:
        await message.answer("Напиши текст відгуку одним повідомленням.")
        return

    if text.startswith("/"):
        await message.answer(
            "Це схоже на команду. Напиши сам текст відгуку або /cancel, щоб скасувати."
        )
        return

    PENDING_FEEDBACK_USERS.discard(user_id)
    save_feedback(message, text)
    await notify_admins_about_feedback(message, text)

    await message.answer("Дякую. Відгук збережено.")
