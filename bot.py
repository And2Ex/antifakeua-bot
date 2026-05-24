from aiogram import Bot, Dispatcher

from config import BOT_TOKEN
from handlers import (
    about,
    admin,
    analytics,
    buy,
    check,
    feedback,
    help,
    limits,
    publish,
    review,
    start,
    transparency,
)


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def setup_routers():
    dp.include_router(start.router)
    dp.include_router(help.router)
    dp.include_router(limits.router)
    dp.include_router(about.router)
    dp.include_router(feedback.router)
    dp.include_router(transparency.router)
    dp.include_router(buy.router)
    dp.include_router(admin.router)
    dp.include_router(publish.router)
    dp.include_router(review.router)
    dp.include_router(analytics.router)
    dp.include_router(check.router)
