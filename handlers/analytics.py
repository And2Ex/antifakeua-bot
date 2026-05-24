"""Optional analytics commands for aiogram 3.x.

Add this router in setup_bot(dp):
    from handlers import analytics
    dp.include_router(analytics.router)
"""

from __future__ import annotations

import sqlite3

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import DATABASE_PATH


router = Router()


@router.message(Command("source"))
async def source_command(message: Message) -> None:
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Надішли так: /source pravda.com.ua або /source @channel")
        return

    query = args[1].strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")

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
        await message.answer("Поки що цього джерела немає в базі.")
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
        "📊 Репутація джерела\n\n"
        f"Джерело: {name}\n"
        f"Тип: {source_type}\n"
        f"Домен: {domain or '—'}\n"
        f"Індекс надійності: {score}/100\n\n"
        f"✅ Правда: {true_count}\n"
        f"❌ Фейки: {fake_count}\n"
        f"⚠️ Маніпуляції: {manipulation_count}\n"
        f"🕒 Старий контент як новий: {stale_count}\n"
        f"❔ Непідтверджено: {unverified_count}"
    )
    await message.answer(text)
