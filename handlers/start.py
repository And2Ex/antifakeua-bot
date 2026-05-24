from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from config import ADMIN_IDS, GITHUB_URL, METHODOLOGY_URL
from database.db import add_user, get_request_by_public_id
from keyboards.menu import (
    BACK_TO_MENU_KEYBOARD,
    FEEDBACK_MENU_KEYBOARD,
    TRANSPARENCY_KEYBOARD,
    get_main_menu_keyboard,
)
from services.limiter import get_limit_info
from services.public_check import format_public_check
from services.gpt import FACT_CHECK_PROMPT
from services.utils import truncate_text


router = Router()

NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


WELCOME_TEXT = (
    "<b>AntiFakeUA_Bot</b> — помічник для перевірки новин, заяв і пересланих дописів.\n\n"
    "Він допомагає швидко зрозуміти, чи є в повідомленні ознаки фейку, маніпуляції, "
    "непідтвердженої інформації або старої новини, поданої як нова.\n\n"
    "<b>Як почати:</b> просто надішли сюди текст новини або перешли допис із Telegram-каналу.\n\n"
    "Для пояснення роботи бота відкрий кнопку нижче."
)


ABOUT_TEXT = (
    "<b>Як користуватись AntiFakeUA_Bot</b>\n\n"
    "<b>В особистому чаті</b>\n"
    "1. Скопіюй текст новини, заяви або підозрілого повідомлення.\n"
    "2. Надішли його боту звичайним повідомленням.\n"
    "3. Отримай вердикт, коротке пояснення та публічне посилання на перевірку.\n\n"
    "<b>У групі</b>\n"
    "• відповідай командою <code>/check</code> на повідомлення, яке треба перевірити;\n"
    "• або напиши <code>/check текст твердження</code>.\n"
    "Так бот не буде втручатися в кожне повідомлення групи.\n\n"
    "<b>Чим бот корисний</b>\n"
    "• відділяє факт від припущення, емоційної подачі й клікбейту;\n"
    "• пояснює, чому твердження виглядає підтвердженим, сумнівним або маніпулятивним;\n"
    "• допомагає помічати старі новини, які знову подають як актуальні;\n"
    "• зберігає результат у форматі посилання, яке можна переслати іншим.\n\n"
    "<b>Важливо:</b> бот дає аргументовану попередню перевірку. Для складних тем результат варто читати разом із джерелами та контекстом."
)


TRANSPARENCY_TEXT = (
    "<b>Посилання і відкритість</b>\n\n"
    "AntiFakeUA_Bot створений так, щоб результат перевірки був не просто коротким ярликом, а поясненням: "
    "що саме стверджується, які є підстави для вердикту і чому повідомлення може бути правдою, "
    "фейком, маніпуляцією або непідтвердженою інформацією.\n\n"
    "Тут можна відкрити матеріали, які допомагають зрозуміти логіку роботи бота."
)


SOURCE_HELP_TEXT = (
    "<b>Репутація джерела</b>\n\n"
    "Бот може показувати накопичену статистику про сайти, домени й Telegram-канали, які вже траплялися в перевірках.\n\n"
    "Це не остаточний “вирок” джерелу, а історія його поведінки в базі AntiFakeUA: "
    "скільки разів воно траплялося у правдивих, сумнівних, маніпулятивних або фейкових повідомленнях.\n\n"
    "Перевірити джерело можна вручну:\n"
    "<code>/source pravda.com.ua</code>\n"
    "або\n"
    "<code>/source @channel</code>"
)


FEEDBACK_TEXT = (
    "<b>Відгук або повідомлення про помилку</b>\n\n"
    "Напиши, що саме не спрацювало або що варто покращити.\n\n"
    "Можна повідомити про:\n"
    "• неточну відповідь;\n"
    "• проблему з оплатою;\n"
    "• незрозумілий текст;\n"
    "• ідею для нової функції.\n\n"
    "Натисни кнопку нижче й надішли відгук наступним повідомленням."
)


def build_transparency_text() -> str:
    links = []

    if GITHUB_URL:
        links.append(f'• <a href="{escape(GITHUB_URL, quote=True)}">GitHub проєкту</a>')

    if METHODOLOGY_URL:
        links.append(f'• <a href="{escape(METHODOLOGY_URL, quote=True)}">Методологія перевірки</a>')

    links.append("• Prompt перевірки можна відкрити кнопкою нижче.")

    return TRANSPARENCY_TEXT + "\n\n" + "\n".join(links)


async def send_main_menu(message: Message, user_id: int) -> None:
    await message.answer(
        WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=user_id in ADMIN_IDS),
        link_preview_options=NO_LINK_PREVIEW,
    )


async def edit_or_send_menu(
    callback: CallbackQuery,
    text: str,
    reply_markup=BACK_TO_MENU_KEYBOARD,
) -> None:
    try:
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            link_preview_options=NO_LINK_PREVIEW,
        )
    except Exception:
        await callback.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
            link_preview_options=NO_LINK_PREVIEW,
        )


@router.message(CommandStart())
async def start_handler(message: Message, command: CommandObject):
    user = message.from_user

    add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    if command.args and command.args.startswith("check_"):
        request = get_request_by_public_id(command.args)

        if request is None:
            await message.answer("Перевірку не знайдено.")
            return

        await message.answer(
            format_public_check(request),
            parse_mode="HTML",
            link_preview_options=NO_LINK_PREVIEW,
        )
        return

    await send_main_menu(message, user.id)


@router.message(Command("menu"))
async def menu_handler(message: Message):
    await send_main_menu(message, message.from_user.id)


@router.callback_query(F.data == "menu:main")
async def menu_main_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=callback.from_user.id in ADMIN_IDS),
        link_preview_options=NO_LINK_PREVIEW,
    )
    await callback.answer()


@router.callback_query(F.data.in_({"menu:how", "menu:about", "menu:trust"}))
async def menu_about_callback(callback: CallbackQuery):
    await edit_or_send_menu(callback, ABOUT_TEXT)
    await callback.answer()


@router.callback_query(F.data == "menu:limits")
async def menu_limits_callback(callback: CallbackQuery):
    await edit_or_send_menu(callback, escape(get_limit_info(callback.from_user.id)))
    await callback.answer()


@router.callback_query(F.data == "menu:source")
async def menu_source_callback(callback: CallbackQuery):
    await edit_or_send_menu(callback, SOURCE_HELP_TEXT)
    await callback.answer()


@router.callback_query(F.data == "menu:feedback")
async def menu_feedback_callback(callback: CallbackQuery):
    await edit_or_send_menu(callback, FEEDBACK_TEXT, reply_markup=FEEDBACK_MENU_KEYBOARD)
    await callback.answer()


@router.callback_query(F.data == "menu:transparency")
async def menu_transparency_callback(callback: CallbackQuery):
    await edit_or_send_menu(callback, build_transparency_text(), reply_markup=TRANSPARENCY_KEYBOARD)
    await callback.answer()


@router.callback_query(F.data == "menu:prompt")
async def menu_prompt_callback(callback: CallbackQuery):
    prompt_text = truncate_text(FACT_CHECK_PROMPT.strip(), 3500)

    await edit_or_send_menu(
        callback,
        "<b>Prompt перевірки</b>\n\n"
        f"<pre>{escape(prompt_text)}</pre>",
        reply_markup=TRANSPARENCY_KEYBOARD,
    )
    await callback.answer()
