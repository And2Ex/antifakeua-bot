import asyncio
import logging

from bot import bot, dp, setup_routers
from config import BOT_TOKEN
from database.db import init_db
from services.commands import setup_bot_commands


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не заданий у .env")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    init_db()
    setup_routers()
    await setup_bot_commands(bot)

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types()
    )


if __name__ == "__main__":
    asyncio.run(main())
