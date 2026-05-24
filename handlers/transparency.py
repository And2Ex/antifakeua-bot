from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions, Message

from handlers.start import build_transparency_text
from keyboards.menu import TRANSPARENCY_KEYBOARD
from services.gpt import FACT_CHECK_PROMPT
from services.utils import truncate_text


router = Router()

NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


@router.message(Command("transparency"))
async def transparency_handler(message: Message):
    await message.answer(
        build_transparency_text(),
        parse_mode="HTML",
        reply_markup=TRANSPARENCY_KEYBOARD,
        link_preview_options=NO_LINK_PREVIEW,
    )


@router.message(Command("prompt"))
async def prompt_handler(message: Message):
    prompt_text = truncate_text(FACT_CHECK_PROMPT.strip(), 3500)

    await message.answer(
        "<b>Prompt перевірки:</b>\n\n"
        f"<pre>{escape(prompt_text)}</pre>",
        parse_mode="HTML",
        reply_markup=TRANSPARENCY_KEYBOARD,
    )
