"""Optional analytics commands for aiogram 3.x."""

from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_connection


router = Router()


@router.message(Command("source"))
async def source_command(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)

    if len(args) < 2:
        await message.answer(
            "<b>Як перевірити джерело</b>\n\n"
            "Надішли команду з доменом або каналом:\n"
            "<code>/source pravda.com.ua</code>\n"
            "<code>/source @channel</code>",
            parse_mode="HTML",
        )
        return

    query = (
        args[1]
        .strip()
        .lower()
        .removeprefix("https://")
        .removeprefix("http://")
        .removeprefix("www.")
    )

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT name, type, domain, true_count, fake_count, manipulation_count,
                   unverified_count, stale_count, reliability_score
            FROM sources
            WHERE lower(name) LIKE %s OR lower(domain) LIKE %s
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (f"%{query}%", f"%{query}%"),
        ).fetchone()

    if not row:
        await message.answer(
            "<b>Джерела поки немає в базі</b>\n\n"
            "Воно зʼявиться після того, як трапиться в одній із перевірок.",
            parse_mode="HTML",
        )
        return

    name = row["name"]
    source_type = row["type"]
    domain = row["domain"]
    true_count = row["true_count"] or 0
    fake_count = row["fake_count"] or 0
    manipulation_count = row["manipulation_count"] or 0
    unverified_count = row["unverified_count"] or 0
    stale_count = row["stale_count"] or 0
    score = row["reliability_score"] or 50

    text = (
        "🌐 <b>Статистика джерела</b>\n\n"
        f"<b>Назва:</b> {escape(name)}\n"
        f"<b>Тип:</b> {escape(source_type)}\n"
        f"<b>Домен:</b> {escape(domain or 'немає')}\n\n"
        f"✅ Правда: {true_count}\n"
        f"❌ Фейк: {fake_count}\n"
        f"⚠️ Маніпуляція: {manipulation_count}\n"
        f"ℹ️ Недостатньо даних: {unverified_count}\n"
        f"🕒 Старий контент: {stale_count}\n\n"
        f"<b>Умовний бал:</b> {float(score):.2f}/100\n\n"
        "Бал є лише внутрішньою статистикою появ джерела в перевірках, а не остаточною оцінкою медіа."
    )

    await message.answer(text, parse_mode="HTML")
