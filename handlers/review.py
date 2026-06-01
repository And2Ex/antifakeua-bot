from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from config import ADMIN_IDS
from database.db import (
    get_next_pending_request,
    get_request_by_public_id,
    update_publication_status,
)
from services.publisher import build_channel_post, publish_check_to_channel
from services.utils import truncate_text


router = Router()

NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def build_review_keyboard(public_id: str, source_link: str | None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text="✅ Опублікувати",
                callback_data=f"review_publish:{public_id}",
            )
        ],
        [
            InlineKeyboardButton(
                text="⏭ Пропустити",
                callback_data=f"review_skip:{public_id}",
            ),
            InlineKeyboardButton(
                text="🗑 Не публікувати",
                callback_data=f"review_reject:{public_id}",
            ),
        ],
    ]

    if source_link:
        rows.append([
            InlineKeyboardButton(
                text="📌 Оригінальний допис",
                url=source_link,
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_review_text(request) -> str:
    request_text = truncate_text(request["request_text"], 800)
    preview_text = build_channel_post(request)
    verdict = request["verdict"] or "Немає"
    source_title = request["source_title"] or "невідомо"

    return (
        "🧾 <b>Перевірка на публікацію</b>\n\n"
        f"<b>ID:</b> {escape(request['public_id'])}\n"
        f"<b>Вердикт:</b> {escape(verdict)}\n"
        f"<b>Опубліковано в:</b> {escape(source_title)}\n\n"
        "<b>Оригінальний текст:</b>\n"
        f"{escape(request_text)}\n\n"
        "<b>Майбутній допис у каналі:</b>\n"
        f"{preview_text}"
    )


async def send_next_review(message: Message):
    request = get_next_pending_request()

    if request is None:
        await message.answer("Немає непереглянутих перевірок.")
        return

    await message.answer(
        build_review_text(request),
        parse_mode="HTML",
        link_preview_options=NO_LINK_PREVIEW,
        reply_markup=build_review_keyboard(
            request["public_id"],
            request["source_link"],
        )
    )


@router.message(Command("review"))
@router.message(F.text == "🧾 Черга публікацій")
async def review_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Ця команда доступна лише адміністратору.")
        return

    await send_next_review(message)


@router.callback_query(F.data.startswith("review_skip:"))
async def review_skip_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    await callback.answer("Пропускаю…")
    public_id = callback.data.split(":", 1)[1]

    update_publication_status(
        public_id=public_id,
        status="skipped"
    )

    await callback.message.edit_text(
        "⏭ Перевірку пропущено.",
        parse_mode="HTML"
    )

    await send_next_review(callback.message)


@router.callback_query(F.data.startswith("review_reject:"))
async def review_reject_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    await callback.answer("Відхиляю…")
    public_id = callback.data.split(":", 1)[1]

    update_publication_status(
        public_id=public_id,
        status="rejected"
    )

    await callback.message.edit_text(
        "🗑 Перевірку позначено як непотрібну для публікації.",
        parse_mode="HTML"
    )

    await send_next_review(callback.message)


@router.callback_query(F.data.startswith("review_publish:"))
async def review_publish_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    public_id = callback.data.split(":", 1)[1]
    request = get_request_by_public_id(public_id)

    if request is None:
        await callback.answer("Перевірку не знайдено.", show_alert=True)
        return

    await callback.answer("Публікую…")
    try:
        published_message = await publish_check_to_channel(
            bot=callback.bot,
            request=request,
        )
    except Exception as error:
        await callback.message.answer(f"Помилка публікації: {error}")
        return

    update_publication_status(
        public_id=public_id,
        status="published",
        published_message_id=published_message.message_id
    )

    await callback.message.edit_text(
        "✅ Перевірку опубліковано в канал.",
        parse_mode="HTML"
    )

    await send_next_review(callback.message)
