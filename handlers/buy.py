from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import add_user, create_payment
from services.payments import create_checkout_url, get_package, get_packages_text, PAYMENT_PACKAGES


router = Router()


def build_buy_keyboard() -> InlineKeyboardMarkup:
    buttons = []

    for package_id, package in PAYMENT_PACKAGES.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"💳 {package['title']} — {package['checks']} перевірок",
                callback_data=f"buy:{package_id}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("buy"))
async def buy_handler(message: Message):
    user = message.from_user

    add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    await message.answer(
        get_packages_text(),
        reply_markup=build_buy_keyboard(),
    )


@router.callback_query(F.data == "buy_menu")
async def buy_menu_callback(callback: CallbackQuery):
    await callback.message.answer(
        get_packages_text(),
        reply_markup=build_buy_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_package_callback(callback: CallbackQuery):
    if callback.data == "buy:menu":
        await callback.message.answer(
            get_packages_text(),
            reply_markup=build_buy_keyboard(),
        )
        await callback.answer()
        return

    package_id = callback.data.split(":", 1)[1]
    package = get_package(package_id)

    if package is None:
        await callback.answer("Пакет не знайдено.", show_alert=True)
        return

    user = callback.from_user

    add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    order_id = create_payment(
        user_id=user.id,
        package_id=package_id,
        package_title=package["title"],
        checks_added=package["checks"],
        amount=package["amount"],
        currency=package["currency"],
    )

    try:
        payment_url = create_checkout_url(order_id, package)
    except ValueError as error:
        await callback.message.answer(
            "Оплата ще не налаштована.\n\n"
            f"Технічна причина: {error}"
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Оплатити через LiqPay",
                    url=payment_url,
                )
            ]
        ]
    )

    await callback.message.answer(
        "Платіж створено.\n\n"
        f"Пакет: {package['title']}\n"
        f"Перевірок: {package['checks']}\n"
        f"Сума: {package['amount']:.0f} {package['currency']}\n\n"
        "Після успішної оплати перевірки автоматично додадуться до твого платного балансу.",
        reply_markup=keyboard,
    )

    await callback.answer()
