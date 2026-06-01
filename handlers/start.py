from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, LinkPreviewOptions, Message

from config import ADMIN_IDS, GITHUB_URL, METHODOLOGY_URL
from database.db import add_user, get_request_by_public_id, get_user
from keyboards.menu import (
    BACK_TO_MENU_KEYBOARD,
    FEEDBACK_MENU_KEYBOARD,
    TRANSPARENCY_KEYBOARD,
    get_main_menu_keyboard,
)
from services.limiter import get_limit_info
from services.public_check import format_public_check
from services.gpt import FACT_CHECK_PROMPT
from services.admin_notifications import notify_new_user
from services.utils import truncate_text


router = Router()

NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


WELCOME_TEXT = (
    "<b>AntiFakeUA_Bot</b> — сервіс швидкої перевірки новин, заяв і пересланих повідомлень.\n\n"
    "Бот допомагає оцінити, чи є в тексті ознаки фейку, маніпуляції, непідтвердженої інформації або старого контенту, поданого як новий.\n\n"
    "<b>Як почати:</b> надішли текст новини або перешли повідомлення з Telegram у цей чат.\n"
    "У групі відповідай командою <code>/check</code> на повідомлення, яке треба перевірити.\n\n"
    "<b>Для адміністраторів каналів:</b> команда <code>/quickcheck</code> дозволяє ввімкнути короткі автоматичні позначки під новинними дописами.\n\n"
    "<i>Примітка: після тривалого простою перша дія може виконуватися з невеликою затримкою, поки сервіс запускається.</i>"
)


ABOUT_TEXT = (
    "<b>Про бота і як користуватись</b>\n\n"
    "<b>Що можна перевіряти</b>\n"
    "• новини та заголовки;\n"
    "• переслані дописи з Telegram;\n"
    "• заяви політиків, блогерів або медіа;\n"
    "• короткі твердження, які потребують перевірки.\n\n"
    "<b>У приватному чаті</b>\n"
    "Надішли текст або перешли повідомлення з Telegram — бот поверне вердикт із короткою причиною, поясненням і джерелами перевірки.\n\n"
    "<b>У групі</b>\n"
    "Відповідай командою <code>/check</code> на потрібне повідомлення.\n\n"
    "<b>Для новинних каналів</b>\n"
    "Адміністратор може відкрити <code>/quickcheck</code> у приватному чаті з ботом і ввімкнути автоматичні короткі позначки. Бот реагує лише на дописи з перевірюваною новиною; рекламу та звичайні повідомлення він не позначає. Натискання на <b>AntiFakeUA</b> у позначці відкриває повний висновок із джерелами.\n\n"
    "<b>Важливо</b>\n"
    "Результат є аргументованою попередньою оцінкою. Для складних або чутливих тем варто додатково звіряти інформацію з першоджерелами.\n\n"
    "<b>Підтримка проєкту</b>\n"
    "Добровільно підтримати AntiFakeUA можна в розділі <b>«Підтримати»</b>. Після переказу відкрий цей розділ і саме там надішли скріншот оплати для отримання додаткового ліміту."
)


TRANSPARENCY_TEXT = (
    "<b>Відкритість і посилання</b>\n\n"
    "AntiFakeUA_Bot показує не лише вердикт, а й пояснення та джерела, на яких ґрунтується висновок.\n\n"
    "Щоб користувач міг сам оцінити підхід, відкрито методологію та prompt перевірки."
)

SOURCE_HELP_TEXT = (
    "<b>Репутація джерела</b>\n\n"
    "Бот поступово накопичує статистику про сайти, домени й Telegram-канали, які трапляються у перевірках.\n\n"
    "Це не остаточний ярлик для джерела, а історія його появ у базі AntiFakeUA.\n\n"
    "<b>Приклади:</b>\n"
    "<code>/source pravda.com.ua</code>\n"
    "<code>/source @channel</code>"
)

FEEDBACK_TEXT = (
    "<b>Відгук або повідомлення про помилку</b>\n\n"
    "Напиши, що саме варто виправити або покращити.\n\n"
    "Можна надіслати:\n"
    "• приклад неточної відповіді;\n"
    "• проблему з підтримкою або лімітом;\n"
    "• ідею для нової функції;\n"
    "• будь-яке зауваження щодо роботи бота.\n\n"
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

    is_new_user = get_user(user.id) is None

    add_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    if is_new_user:
        await notify_new_user(
            message.bot,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
        )

    if command.args and command.args.startswith("check_"):
        request = get_request_by_public_id(command.args)

        if request is None:
            await message.answer(
                "<b>Перевірку не знайдено</b>\n\n"
                "Можливо, посилання застаріле або код перевірки неправильний.",
                parse_mode="HTML",
            )
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
    await callback.answer()
    await callback.message.edit_text(
        WELCOME_TEXT,
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(is_admin=callback.from_user.id in ADMIN_IDS),
        link_preview_options=NO_LINK_PREVIEW,
    )


@router.callback_query(F.data.in_({"menu:how", "menu:about", "menu:trust"}))
async def menu_about_callback(callback: CallbackQuery):
    await callback.answer()
    await edit_or_send_menu(callback, ABOUT_TEXT)


@router.callback_query(F.data == "menu:limits")
async def menu_limits_callback(callback: CallbackQuery):
    await callback.answer()
    await edit_or_send_menu(callback, get_limit_info(callback.from_user.id))


@router.callback_query(F.data == "menu:source")
async def menu_source_callback(callback: CallbackQuery):
    await callback.answer()
    await edit_or_send_menu(callback, SOURCE_HELP_TEXT)


@router.callback_query(F.data == "menu:feedback")
async def menu_feedback_callback(callback: CallbackQuery):
    await callback.answer()
    await edit_or_send_menu(callback, FEEDBACK_TEXT, reply_markup=FEEDBACK_MENU_KEYBOARD)


@router.callback_query(F.data == "menu:transparency")
async def menu_transparency_callback(callback: CallbackQuery):
    await callback.answer()
    await edit_or_send_menu(callback, build_transparency_text(), reply_markup=TRANSPARENCY_KEYBOARD)


@router.callback_query(F.data == "menu:prompt")
async def menu_prompt_callback(callback: CallbackQuery):
    await callback.answer()
    prompt_text = truncate_text(FACT_CHECK_PROMPT.strip(), 3500)

    await edit_or_send_menu(
        callback,
        "<b>Prompt перевірки</b>\n\n"
        f"<pre>{escape(prompt_text)}</pre>",
        reply_markup=TRANSPARENCY_KEYBOARD,
    )
