from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database.db import (
    add_user,
    consume_donation_intent,
    create_donation_submission,
    set_donation_intent,
)
from keyboards.support import build_support_keyboard
from services.admin_notifications import notify_donation_screenshot


router = Router()


SUPPORT_TEXT = (
    "💙 <b>Підтримати AntiFakeUA</b>\n\n"
    "AntiFakeUA має безкоштовний ліміт перевірок для всіх користувачів. "
    "Підтримати розвиток проєкту можна добровільним переказом на банку Monobank.\n\n"
    "Після підтримки адміністратор може вручну надати додатковий ліміт перевірок як подяку. "
    "Сума підтримки довільна, а додатковий ліміт визначається після перевірки переказу.\n\n"
    "<b>Як підтвердити підтримку:</b>\n"
    "1. Відкрий банку кнопкою нижче й зроби переказ.\n"
    "2. Після переказу відкрий або ще раз відкрий пункт <b>«Підтримати»</b>.\n"
    "3. Надішли в цей чат скріншот оплати — він буде переданий адміністратору.\n"
    "4. Після перевірки ти отримаєш повідомлення про наданий додатковий ліміт.\n\n"
    "<i>Часового обмеження немає: після відкриття цього розділу бот прийме наступне надіслане фото як скріншот підтримки.</i>"
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

    if not consume_donation_intent(user.id):
        await message.answer(
            "<b>Зображення поки що не аналізуються</b>\n\n"
            "Якщо на зображенні є текст новини, надішли його текстом.\n\n"
            "Якщо це скріншот підтримки AntiFakeUA, спочатку відкрий розділ "
            "<code>/support</code>, а потім надішли скріншот ще раз.",
            parse_mode="HTML",
        )
        return

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
        "Скріншот отримано. Після перевірки переказу адміністратор вручну надасть додатковий ліміт перевірок.\n\n"
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
