from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from config import (
    FREE_TEXT_LIMIT,
    PACKAGE_BASIC_CHECKS,
    PACKAGE_BASIC_PRICE_UAH,
    PACKAGE_PRO_CHECKS,
    PACKAGE_PRO_PRICE_UAH,
)
from database.db import (
    add_user,
    consume_donation_intent,
    create_donation_submission,
    has_donation_intent,
    set_donation_intent,
)
from keyboards.support import build_support_keyboard
from services.admin_notifications import notify_donation_screenshot


router = Router()


SUPPORT_TEXT = (
    "💙 <b>Підтримати AntiFakeUA й отримати перевірки</b>\n\n"
    f"Щомісяця доступно <b>{FREE_TEXT_LIMIT} безкоштовних перевірок</b>. "
    "Для додаткових перевірок обери пакет:\n\n"
    "<b>Пакети додаткових перевірок:</b>\n"
    f"• <b>+{PACKAGE_BASIC_CHECKS}</b> перевірок — <b>{PACKAGE_BASIC_PRICE_UAH} грн</b>\n"
    f"• <b>+{PACKAGE_PRO_CHECKS}</b> перевірок — <b>{PACKAGE_PRO_PRICE_UAH} грн</b>\n\n"
    "Додаткові перевірки додаються до балансу й не згорають після щомісячного оновлення безкоштовного ліміту.\n\n"
    "<b>Як отримати пакет:</b>\n"
    "1. Відкрий банку кнопкою нижче й зроби переказ на суму обраного пакета.\n"
    "2. Після переказу повернися до бота й відкрий пункт <b>«Підтримати»</b>.\n"
    "3. Саме в розділі <b>«Підтримати»</b> надішли скріншот оплати — він буде переданий адміністратору.\n"
    "4. Після підтвердження суми пакет буде додано до твого балансу.\n\n"
    "<i>Скріншот оплати потрібно надсилати саме в розділі «Підтримати».</i>"
)


async def show_support_menu(message: Message) -> None:
    user = message.from_user

    if user is None:
        return

    add_user(user_id=user.id, username=user.username, first_name=user.first_name)
    set_donation_intent(user.id)

    await message.answer(
        SUPPORT_TEXT,
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
        "Скріншот отримано. Після перевірки суми адміністратор додасть відповідний пакет перевірок.\n\n"
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
