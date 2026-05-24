import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

from aiogram import Bot
from fastapi import FastAPI, HTTPException, Request

from config import BASE_DIR, BOT_TOKEN
from database.db import process_successful_payment
from services.payments import decode_callback_data, verify_callback_signature


app = FastAPI(title="AntiFakeUA_Bot payments")
LOG_DIR = BASE_DIR / "logs"
CALLBACK_LOG_PATH = LOG_DIR / "liqpay_callbacks.log"


def write_callback_log(payload: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **payload,
    }

    with open(CALLBACK_LOG_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


@app.get("/")
async def root():
    return {"status": "ok", "service": "AntiFakeUA_Bot payment webhook"}


@app.post("/liqpay/callback")
async def liqpay_callback(request: Request):
    body = (await request.body()).decode("utf-8")
    form_data = parse_qs(body)

    data = form_data.get("data", [None])[0]
    signature = form_data.get("signature", [None])[0]

    if not data or not signature:
        write_callback_log({
            "ok": False,
            "stage": "parse",
            "error": "missing_data_or_signature",
            "body": body[:1000],
        })
        raise HTTPException(status_code=400, detail="Missing data or signature")

    if not verify_callback_signature(data, signature):
        write_callback_log({
            "ok": False,
            "stage": "signature",
            "error": "invalid_signature",
            "body": body[:1000],
        })
        raise HTTPException(status_code=400, detail="Invalid signature")

    callback_data = decode_callback_data(data)
    order_id = callback_data.get("order_id")

    if not order_id:
        write_callback_log({
            "ok": False,
            "stage": "decode",
            "error": "missing_order_id",
            "callback_data": callback_data,
        })
        raise HTTPException(status_code=400, detail="Missing order_id")

    result = process_successful_payment(
        order_id=order_id,
        callback_data=callback_data,
    )

    write_callback_log({
        "ok": True,
        "stage": "processed",
        "order_id": order_id,
        "callback_status": callback_data.get("status"),
        "callback_data": callback_data,
        "result": result,
    })

    if result.get("credited"):
        bot = Bot(token=BOT_TOKEN)

        try:
            await bot.send_message(
                chat_id=result["user_id"],
                text=(
                    "Оплату отримано.\n\n"
                    f"Пакет: {result.get('package_title', 'платний пакет')}\n"
                    f"Додано перевірок: {result['checks_added']}\n\n"
                    "Перевірити баланс можна командою /limits."
                ),
            )
        finally:
            await bot.session.close()

    return {"status": "ok", "result": result}
