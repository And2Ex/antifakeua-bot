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
    get_pending_publication_requests,
    get_request_by_public_id,
    save_publication_draft,
    skip_pending_publication_requests_through,
    update_publication_status,
)
from services.formatter import VERDICT_EMOJIS, clean_model_text
from services.progress import safe_delete_message
from services.publication import generate_publication_draft
from services.publisher import (
    build_channel_post,
    get_saved_media,
    get_saved_publication,
    get_saved_result,
    publish_check_to_channel,
)
from services.quick_verdict import build_public_check_url
from services.utils import truncate_text


router = Router()

NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)
QUEUE_PAGE_SIZE = 10


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def has_media(request) -> bool:
    return bool(get_saved_media(request))


def build_open_publication_keyboard(public_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📰 Публікація",
                    callback_data=f"review_open:{public_id}",
                )
            ]
        ]
    )


def build_publication_action_keyboard(request) -> InlineKeyboardMarkup:
    public_id = request["public_id"]
    rows = []

    if has_media(request):
        rows.append([
            InlineKeyboardButton(
                text="✅ Опублікувати з медіа",
                callback_data=f"review_publish_media:{public_id}",
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="✅ Опублікувати без медіа",
                callback_data=f"review_publish:{public_id}",
            )
        ])
    else:
        rows.append([
            InlineKeyboardButton(
                text="✅ Опублікувати",
                callback_data=f"review_publish:{public_id}",
            )
        ])

    rows.append([
        InlineKeyboardButton(
            text="⏭ Не публікувати",
            callback_data=f"review_skip:{public_id}",
        ),
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_queue_title(request) -> str:
    result = get_saved_result(request) or {}
    title = clean_model_text(str(result.get("queue_title", "")).strip())

    if not title:
        title = clean_model_text(str(result.get("summary", "")).strip())

    if not title:
        title = clean_model_text(str(request.get("request_text", "")).strip())

    return truncate_text(title or "Перевірка без заголовка", 92)


def build_queue_text(requests: list) -> str:
    lines = [
        "🧾 <b>Непереглянуті перевірки для публікації</b>",
        "",
        "Відкрий потрібний заголовок, переглянь фактчек і натисни <b>«📰 Публікація»</b>. "
        "Лише після цього бот сформує готовий допис для каналу.",
        "",
    ]

    for index, request in enumerate(requests, start=1):
        verdict = request.get("verdict") or "Недостатньо даних"
        emoji = VERDICT_EMOJIS.get(verdict, "ℹ️")
        title = get_queue_title(request)
        url = build_public_check_url(request["public_id"])
        label = f"{emoji} {verdict} — {title}"
        lines.append(
            f'{index}. <a href="{escape(url, quote=True)}">{escape(label)}</a>'
        )

    lines.extend([
        "",
        "<i>Кнопка «Наступні 10» позначить усі перевірки цієї сторінки як пропущені "
        "та очистить їхні медіа з черги.</i>",
    ])

    return "\n".join(lines)


def build_queue_keyboard(requests: list) -> InlineKeyboardMarkup:
    rows = []

    if requests:
        last_id = requests[-1]["id"]
        rows.append([
            InlineKeyboardButton(
                text="Наступні 10 ⏭",
                callback_data=f"review_page_next:{last_id}",
            ),
            InlineKeyboardButton(
                text="🔄 Оновити",
                callback_data="review_page_refresh",
            ),
        ])

    rows.append([
        InlineKeyboardButton(
            text="⬅️ До адмін-панелі",
            callback_data="admin:menu",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def ensure_publication_draft(message: Message, request):
    if get_saved_publication(request) is not None:
        return request

    fact_check = get_saved_result(request)

    if fact_check is None:
        raise ValueError("У перевірці немає збереженого результату фактчеку.")

    status_message = await message.answer(
        "Формую готовий новинний допис для каналу…",
        disable_notification=True,
    )

    try:
        publication = await generate_publication_draft(request, fact_check)
        save_publication_draft(request["public_id"], publication)
        updated_request = get_request_by_public_id(request["public_id"])

        if updated_request is None:
            raise ValueError("Не вдалося повторно відкрити перевірку.")

        return updated_request
    finally:
        await safe_delete_message(status_message)


async def send_media_preview(message: Message, request) -> None:
    media_items = get_saved_media(request)

    if not media_items:
        return

    caption = "🖼 <b>Медіа, яке можна додати до публікації</b>"

    if len(media_items) == 1:
        item = media_items[0]
        media_type = item.get("type")
        file_id = item.get("file_id")

        if media_type == "photo":
            await message.answer_photo(photo=file_id, caption=caption, parse_mode="HTML")
            return

        if media_type == "video":
            await message.answer_video(video=file_id, caption=caption, parse_mode="HTML")
            return

        if media_type == "animation":
            await message.answer_animation(animation=file_id, caption=caption, parse_mode="HTML")
            return

        if media_type == "document":
            await message.answer_document(document=file_id, caption=caption, parse_mode="HTML")
            return

    await message.answer(
        f"🖼 <b>Медіа, яке можна додати до публікації:</b> {len(media_items)} файлів.",
        parse_mode="HTML",
    )

    for item in media_items[:10]:
        media_type = item.get("type")
        file_id = item.get("file_id")

        if media_type == "photo":
            await message.answer_photo(photo=file_id, disable_notification=True)
        elif media_type == "video":
            await message.answer_video(video=file_id, disable_notification=True)
        elif media_type == "animation":
            await message.answer_animation(animation=file_id, disable_notification=True)
        elif media_type == "document":
            await message.answer_document(document=file_id, disable_notification=True)


async def send_publication_draft(message: Message, request) -> None:
    if not request.get("is_publishable", False):
        await message.answer("Ця перевірка не призначена для публікації.")
        return

    if request.get("publication_status") != "pending":
        await message.answer("Цю перевірку вже опрацьовано в черзі публікацій.")
        return

    try:
        request = await ensure_publication_draft(message, request)
        post_text = build_channel_post(request)
    except Exception as error:
        await message.answer(f"Не вдалося сформувати допис: {escape(str(error))}", parse_mode="HTML")
        return

    await send_media_preview(message, request)
    await message.answer(
        post_text,
        parse_mode="HTML",
        link_preview_options=NO_LINK_PREVIEW,
        reply_markup=build_publication_action_keyboard(request),
    )


async def send_review_queue(message: Message, *, edit: bool = False) -> None:
    requests = get_pending_publication_requests(limit=QUEUE_PAGE_SIZE)

    if not requests:
        text = "🧾 <b>Черга публікацій</b>\n\nНемає непереглянутих перевірок."
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ До адмін-панелі", callback_data="admin:menu")]
            ]
        )
    else:
        text = build_queue_text(requests)
        keyboard = build_queue_keyboard(requests)

    if edit:
        try:
            await message.edit_text(
                text,
                parse_mode="HTML",
                link_preview_options=NO_LINK_PREVIEW,
                reply_markup=keyboard,
            )
            return
        except Exception:
            pass

    await message.answer(
        text,
        parse_mode="HTML",
        link_preview_options=NO_LINK_PREVIEW,
        reply_markup=keyboard,
    )


@router.message(Command("review"))
@router.message(F.text == "🧾 Черга публікацій")
async def review_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Ця команда доступна лише адміністратору.")
        return

    await send_review_queue(message)


@router.callback_query(F.data.startswith("review_open:"))
async def review_open_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    public_id = callback.data.split(":", 1)[1]
    request = get_request_by_public_id(public_id)

    if request is None:
        await callback.answer("Перевірку не знайдено.", show_alert=True)
        return

    await callback.answer("Формую публікацію…")
    await send_publication_draft(callback.message, request)


@router.callback_query(F.data == "review_page_refresh")
async def review_page_refresh_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    await callback.answer("Список оновлено")
    await send_review_queue(callback.message, edit=True)


@router.callback_query(F.data.startswith("review_page_next:"))
async def review_page_next_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    try:
        last_id = int(callback.data.split(":", 1)[1])
    except (TypeError, ValueError):
        await callback.answer("Некоректна сторінка.", show_alert=True)
        return

    skipped_count = skip_pending_publication_requests_through(last_id)
    await callback.answer(f"Пропущено: {skipped_count}")
    await send_review_queue(callback.message, edit=True)


@router.callback_query(F.data.startswith("review_reject:"))
async def review_reject_compatibility_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    await callback.answer("Не публікую…")
    public_id = callback.data.split(":", 1)[1]

    update_publication_status(
        public_id=public_id,
        status="rejected",
        clear_media=True,
    )

    await callback.message.edit_text(
        "🗑 Допис не буде опубліковано. Медіа із заявки очищено.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("review_skip:"))
async def review_skip_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Недостатньо прав.", show_alert=True)
        return

    await callback.answer("Не публікую…")
    public_id = callback.data.split(":", 1)[1]

    update_publication_status(
        public_id=public_id,
        status="skipped",
        clear_media=True,
    )

    await callback.message.edit_text(
        "⏭ Допис не буде опубліковано. Медіа із заявки очищено.",
        parse_mode="HTML",
    )


async def publish_review(callback: CallbackQuery, include_media: bool) -> None:
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
            include_media=include_media,
        )
    except Exception as error:
        await callback.message.answer(f"Помилка публікації: {escape(str(error))}", parse_mode="HTML")
        return

    update_publication_status(
        public_id=public_id,
        status="published",
        published_message_id=published_message.message_id,
        clear_media=True,
    )

    suffix = "з медіа" if include_media else "без медіа"

    await callback.message.edit_text(
        f"✅ Допис опубліковано в канал {suffix}. Медіа із заявки очищено.",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("review_publish_media:"))
async def review_publish_media_callback(callback: CallbackQuery):
    await publish_review(callback, include_media=True)


@router.callback_query(F.data.startswith("review_publish:"))
async def review_publish_callback(callback: CallbackQuery):
    await publish_review(callback, include_media=False)
