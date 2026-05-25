"""Optional analytics commands for aiogram 3.x."""

from __future__ import annotations

import sqlite3
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import DATABASE_PATH


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

    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT name, type, domain, true_count, fake_count, manipulation_count,
                   unverified_count, stale_count, reliability_score
            FROM sources
            WHERE lower(name) LIKE ? OR lower(domain) LIKE ?
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
        "<b>Репутація джерела</b>\n\n"
        f"<b>Джерело:</b> {escape(str(name))}\n"
        f"<b>Тип:</b> {escape(str(source_type))}\n"
        f"<b>Домен:</b> {escape(str(domain or '—'))}\n"
        f"<b>Індекс надійності:</b> {score}/100\n\n"
        f"<b>Правда:</b> {true_count}\n"
        f"<b>Фейки:</b> {fake_count}\n"
        f"<b>Маніпуляції:</b> {manipulation_count}\n"
        f"<b>Старий контент як новий:</b> {stale_count}\n"
        f"<b>Непідтверджено:</b> {unverified_count}"
    )

    await message.answer(text, parse_mode="HTML")
