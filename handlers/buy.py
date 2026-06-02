from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database.db import (
    add_user,
    consume_donation_intent,
    create_donation_submission,
    get_default_free_limit,
    has_donation_intent,
    set_donation_intent,
)
from keyboards.support import build_support_keyboard
from services.admin_notifications import notify_donation_screenshot


router = Router()


def build_support_text() -> str:
    free_limit = get_default_free_limit()

    return (
        "💙 <b>Підтримати AntiFakeUA</b>\n\n"
        f"Щомісяця доступно <b>{free_limit} безкоштовних перевірок</b>. "
        "Користувачі, які підтримали проєкт, можуть отримати додаткові перевірки.\n\n"
        "Додаткові перевірки додаються до балансу й не згорають після щомісячного оновлення безкоштовного ліміту.\n\n"
        "<b>Як передати підтвердження підтримки:</b>\n"
        "1. Відкрий банку кнопкою нижче та підтримай проєкт.\n"
        "2. Повернися до бота й відкрий пункт <b>«Підтримати»</b>.\n"
        "3. Саме в цьому розділі надішли скріншот підтримки — він буде переданий адміністратору.\n\n"
        "<i>Скріншот потрібно надсилати саме в розділі «Підтримати».</i>"
    )


async def show_support_menu(message: Message) -> None:
    user = message.from_user

    if user is None:
        return

    add_user(user_id=user.id, username=user.username, first_name=user.first_name)
    set_donation_intent(user.id)

    await message.answer(
        build_support_text(),
        parse_mode="HTML",
        reply_markup=build_support_keyboard(),
        disable_notification=True,
    )


@router.message(Command("support", "buy"))
async def support_handler(message: Message):
    await show_support_menu(message)


@router.callback_query(F.data.in_({"support:open", "buy_menu"}))
async def support_menu_callback(callback: CallbackQuery):
    await callback.answer()
    await show_support_menu(callback.message)


@router.message(F.chat.type == "private", F.photo)
async def donation_screenshot_handler(message: Message):
    user = message.from_user

    if user is None:
        return

    if not has_donation_intent(user.id):
        if message.media_group_id:
            from handlers.check import remember_media_group_message

            remember_media_group_message(message)
            return

        if message.caption:
            from handlers.check import get_message_media, process_text_check

            media_item = get_message_media(message)
            await process_text_check(
                requester_message=message,
                text=message.caption,
                media=[media_item] if media_item else None,
                media_group_id=message.media_group_id,
            )
            return

        await message.answer(
            "<b>Зображення поки що не аналізуються</b>\n\n"
            "Якщо медіа має опис із новиною, бот перевірить саме цей опис як текст. "
            "Якщо новина написана тільки на зображенні, скопіюй її текст і надішли окремим повідомленням.\n\n"
            "Якщо це скріншот підтримки AntiFakeUA, відкрий розділ "
            "<b>«Підтримати»</b> і саме там надішли скріншот ще раз.",
            parse_mode="HTML",
        )
        return

    consume_donation_intent(user.id)

    add_user(user_id=user.id, username=user.username, first_name=user.first_name)
    photo = message.photo[-1]
    submission_id = create_donation_submission(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        file_id=photo.file_id,
        file_unique_id=photo.file_unique_id,
        caption=message.caption,
    )

    await message.answer(
        "💙 <b>Дякуємо за підтримку AntiFakeUA</b>\n\n"
        "Скріншот отримано. Після розгляду підтримки адміністратор може додати додаткові перевірки.\n\n"
        "Коли ліміт буде додано, ти отримаєш окреме повідомлення тут у боті.",
        parse_mode="HTML",
    )

    await notify_donation_screenshot(
        message.bot,
        submission_id=submission_id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        photo_file_id=photo.file_id,
    )
