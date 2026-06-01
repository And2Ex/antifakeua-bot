from aiogram import Router
from aiogram.types import ChatMemberUpdated

from services.admin_notifications import notify_new_group


router = Router()


@router.my_chat_member()
async def bot_chat_member_handler(event: ChatMemberUpdated):
    old_status = getattr(event.old_chat_member, "status", None)
    new_status = getattr(event.new_chat_member, "status", None)

    if old_status in {"member", "administrator"}:
        return

    if new_status not in {"member", "administrator"}:
        return

    if event.chat.type not in {"group", "supergroup", "channel"}:
        return

    await notify_new_group(
        event.bot,
        chat_id=event.chat.id,
        title=event.chat.title,
        chat_type=event.chat.type,
    )
