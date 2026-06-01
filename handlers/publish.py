from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import ADMIN_IDS
from database.db import get_request_by_public_id, update_publication_status
from services.publisher import publish_check_to_channel


router = Router()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@router.message(Command("publish"))
async def publish_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Ця команда доступна лише адміністратору.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) != 2:
        await message.answer(
            "Неправильний формат.\n\n"
            "Приклад:\n"
            "/publish check_xxxxx"
        )
        return

    public_id = parts[1].strip()
    request = get_request_by_public_id(public_id)

    if request is None:
        await message.answer("Перевірку не знайдено.")
        return

    try:
        published_message = await publish_check_to_channel(
            bot=message.bot,
            request=request,
        )
    except Exception as error:
        await message.answer(f"Не вдалося опублікувати: {error}")
        return

    update_publication_status(
        public_id=public_id,
        status="published",
        published_message_id=published_message.message_id
    )

    await message.answer(
        "Перевірку опубліковано в канал.\n\n"
        f"message_id: {published_message.message_id}"
    )
