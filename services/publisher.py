from aiogram import Bot
from aiogram.types import LinkPreviewOptions

from config import CHANNEL_ID
from services.utils import escape_html, truncate_text


NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


def build_channel_post(request, public_link: str) -> str:
    response_text = request["response_text"] or "Текст перевірки не збережено."
    request_text = truncate_text(request["request_text"], 700)
    source_link = request["source_link"]

    parts = [
        response_text,
        "",
        "<b>Перевірений текст:</b>",
        escape_html(request_text),
    ]

    if source_link:
        parts.extend([
            "",
            f'📌 <a href="{escape_html(source_link)}">Оригінальний допис</a>',
        ])

    parts.extend([
        f'🔗 <a href="{escape_html(public_link)}">Публічна перевірка</a>',
        "Перевірено через @AntiFakeUA_Bot",
    ])

    return truncate_text("\n".join(parts).strip(), 4000)


async def publish_check_to_channel(bot: Bot, request, public_link: str):
    if not CHANNEL_ID:
        raise ValueError("CHANNEL_ID не заданий у .env")

    post_text = build_channel_post(request, public_link)

    return await bot.send_message(
        chat_id=CHANNEL_ID,
        text=post_text,
        parse_mode="HTML",
        link_preview_options=NO_LINK_PREVIEW,
        disable_notification=True
    )
