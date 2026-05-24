from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from handlers.start import ABOUT_TEXT
from keyboards.menu import BACK_TO_MENU_KEYBOARD


router = Router()


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        ABOUT_TEXT,
        parse_mode="HTML",
        reply_markup=BACK_TO_MENU_KEYBOARD,
    )
