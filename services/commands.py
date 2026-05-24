from aiogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
)

from config import ADMIN_IDS


async def setup_bot_commands(bot):
    private_commands = [
        BotCommand(command="start", description="запуск і головне меню"),
    ]

    await bot.set_my_commands(
        commands=private_commands,
        scope=BotCommandScopeAllPrivateChats(),
    )

    group_commands = [
        BotCommand(command="check", description="перевірити повідомлення через reply"),
    ]

    await bot.set_my_commands(
        commands=group_commands,
        scope=BotCommandScopeAllGroupChats(),
    )

    admin_commands = private_commands + [
        BotCommand(command="admin", description="адмін-панель"),
    ]

    for admin_id in ADMIN_IDS:
        await bot.set_my_commands(
            commands=admin_commands,
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
