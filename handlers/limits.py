from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from services.limiter import get_limit_info


router = Router()


@router.message(Command("limits"))
async def limits_handler(message: Message):
    limit_info = get_limit_info(message.from_user.id)

    await message.answer(limit_info, parse_mode="HTML")
