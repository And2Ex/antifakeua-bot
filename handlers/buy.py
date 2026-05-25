from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import add_user, create_payment
from services.payments import (
    PAYMENT_PACKAGES,
    create_checkout_url,
    format_package_price,
    get_package,
    get_packages_text,
)


router = Router()


def build_buy_keyboard() -> InlineKeyboardMarkup:
    buttons = []

    for package_id, package in PAYMENT_PACKAGES.items():
        buttons.append([
            InlineKeyboardButton(
                text=f"{package['title']} — {package['checks']} перевірок • {package['amount']:.0f} грн",
                callback_data=f"buy:{package_id}",
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_payment_text(package: dict) -> str:
    lines = [
        "<b>Пакет готовий до активації</b>",
        "",
        f"<b>Пакет:</b> {package['title']}",
        f"<b>Перевірок:</b> {package['checks']}",
        f"<b>Ціна:</b> {format_package_price(package)}",
        "",
        "Натисни кнопку нижче, щоб перейти до підтвердження через LiqPay. Після успішного підтвердження перевірки автоматично додадуться до твого балансу.",
    ]

    return "\n".join(lines)


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
        parse_mode="HTML",
        reply_markup=build_buy_keyboard(),
    )


@router.callback_query(F.data == "buy_menu")
async def buy_menu_callback(callback: CallbackQuery):
    await callback.message.answer(
        get_packages_text(),
        parse_mode="HTML",
        reply_markup=build_buy_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_package_callback(callback: CallbackQuery):
    if callback.data == "buy:menu":
        await callback.message.answer(
            get_packages_text(),
            parse_mode="HTML",
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
            "<b>Оплата тимчасово недоступна</b>\n\n"
            "Не вдалося створити платіжне посилання. Спробуй пізніше або напиши через розділ <b>Відгук</b>.\n\n"
            f"<i>Технічна причина: {error}</i>",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Оплатити через LiqPay",
                    url=payment_url,
                )
            ]
        ]
    )

    await callback.message.answer(
        build_payment_text(package),
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    await callback.answer()
