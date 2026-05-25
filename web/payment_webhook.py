import json
import logging
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import parse_qs

from aiogram import Bot
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from config import BASE_DIR, BASE_WEBHOOK_URL, BOT_TOKEN, GITHUB_URL, LIQPAY_SANDBOX, METHODOLOGY_URL, PAYMENT_RESULT_URL, SUPPORT_JAR_URL
from database.db import process_successful_payment
from services.admin_notifications import notify_payment_credited
from services.payments import decode_callback_data, verify_callback_signature


app = FastAPI(title="AntiFakeUA_Bot")
LOG_DIR = BASE_DIR / "logs"
CALLBACK_LOG_PATH = LOG_DIR / "liqpay_callbacks.log"
TELEGRAM_WEBHOOK_PATH = "/telegram/webhook"
LIQPAY_CALLBACK_PATH = "/liqpay/callback"


def write_callback_log(payload: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    record = {
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **payload,
    }

    with open(CALLBACK_LOG_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def render_homepage() -> str:
    bot_url = PAYMENT_RESULT_URL or "https://t.me/AntiFakeUA_Bot"
    github_link = (
        f'<a href="{escape(GITHUB_URL, quote=True)}">GitHub</a>'
        if GITHUB_URL
        else "GitHub буде додано після публікації репозиторію"
    )
    methodology_link = (
        f'<a href="{escape(METHODOLOGY_URL, quote=True)}">Методологія</a>'
        if METHODOLOGY_URL
        else "методологія доступна в боті та репозиторії"
    )

    return f"""
<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AntiFakeUA Bot</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, sans-serif;
      background: #f5f7fb;
      color: #172033;
      line-height: 1.55;
    }}
    main {{
      max-width: 860px;
      margin: 0 auto;
      padding: 40px 18px;
    }}
    .card {{
      background: white;
      border-radius: 18px;
      padding: 26px;
      margin: 18px 0;
      box-shadow: 0 10px 30px rgba(20, 35, 70, 0.08);
    }}
    h1 {{ margin-top: 0; font-size: 34px; }}
    h2 {{ margin-bottom: 8px; }}
    a.button {{
      display: inline-block;
      background: #1f6feb;
      color: white;
      text-decoration: none;
      padding: 12px 18px;
      border-radius: 12px;
      font-weight: bold;
    }}
    .muted {{ color: #5d6b82; }}
    ul {{ padding-left: 22px; }}
    code {{ background: #eef2f8; padding: 2px 6px; border-radius: 6px; }}
  </style>
</head>
<body>
<main>
  <section class="card">
    <h1>AntiFakeUA Bot</h1>
    <p><b>AntiFakeUA</b> — Telegram-бот для перевірки новин, заяв і пересланих повідомлень на ознаки фейків, маніпуляцій, непідтвердженої інформації або старого контенту, поданого як новий.</p>
    <p><a class="button" href="{escape(bot_url, quote=True)}">Відкрити Telegram-бота</a></p>
    <p class="muted">Основний сервіс працює в Telegram. Ця сторінка містить короткий опис послуги, контакт і правила використання.</p>
  </section>

  <section class="card">
    <h2>Що робить бот</h2>
    <ul>
      <li>перевіряє текстові новини, заяви й переслані дописи;</li>
      <li>пояснює, яке саме твердження аналізується;</li>
      <li>показує аргументований попередній висновок;</li>
      <li>допомагає помічати фейки, маніпуляції, клікбейт і підміну контексту;</li>
      <li>зберігає результат перевірки для повторного використання.</li>
    </ul>
  </section>

  <section class="card">
    <h2>Платні пакети</h2>
    <p>Оплата відкриває додаткові перевірки в боті.</p>
    <ul>
      <li>Basic — пакет перевірок для особистого використання;</li>
      <li>Pro — більший пакет для активнішого користування.</li>
    </ul>
    <p>Актуальні ціни та кількість перевірок показуються безпосередньо в Telegram-боті перед активацією пакета.</p>
  </section>

  <section class="card">
    <h2>Повернення коштів</h2>
    <p>Повернення можливе протягом 14 днів, якщо оплачений пакет не був використаний. Для запиту напишіть на email, вказавши Telegram username, дату платежу й суму.</p>
  </section>

  <section class="card">
    <h2>Контакти і відкритість</h2>
    <p>Email: <a href="mailto:and3ex+antifakeua@gmail.com">and3ex+antifakeua@gmail.com</a></p>
    <p>Telegram: <a href="{escape(bot_url, quote=True)}">{escape(bot_url)}</a></p>
    <p>{github_link}</p>
    <p>{methodology_link}</p>
  </section>
</main>
</body>
</html>
"""


@app.on_event("startup")
async def startup_event():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    from bot import bot as telegram_bot, dp, setup_routers
    from database.db import init_db
    from services.commands import setup_bot_commands

    init_db()
    setup_routers()
    await setup_bot_commands(telegram_bot)

    if BASE_WEBHOOK_URL:
        webhook_url = f"{BASE_WEBHOOK_URL}{TELEGRAM_WEBHOOK_PATH}"
        await telegram_bot.delete_webhook(drop_pending_updates=False)
        await telegram_bot.set_webhook(
            url=webhook_url,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=False,
        )
        logging.info("Telegram webhook set to %s", webhook_url)
    else:
        logging.warning("BASE_WEBHOOK_URL is empty. Telegram webhook was not set.")


@app.on_event("shutdown")
async def shutdown_event():
    from bot import bot as telegram_bot

    await telegram_bot.session.close()


@app.get("/", response_class=HTMLResponse)
async def root():
    return render_homepage()


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post(TELEGRAM_WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    from bot import bot as telegram_bot, dp

    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": telegram_bot})
        await dp.feed_update(telegram_bot, update)
    except Exception as error:
        logging.exception("Telegram webhook processing error: %s", error)
        raise HTTPException(status_code=500, detail="Telegram webhook error")

    return {"ok": True}


@app.post(LIQPAY_CALLBACK_PATH)
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
            if LIQPAY_SANDBOX:
                support_line = (
                    f'\n\nПідтримати проєкт можна добровільно:\n'
                    f'<a href="{SUPPORT_JAR_URL}">Monobank Банка AntiFakeUA</a>'
                    if SUPPORT_JAR_URL
                    else ""
                )

                success_text = (
                    "<b>Пакет активовано</b>\n\n"
                    f"<b>Пакет:</b> {result.get('package_title', 'платний пакет')}\n"
                    f"<b>Додано перевірок:</b> {result['checks_added']}\n\n"
                    "Зараз оплата працює в тестовому форматі, тому кошти з картки не списуються."
                    f"{support_line}\n\n"
                    "Поточний баланс можна переглянути командою <code>/limits</code>."
                )
            else:
                success_text = (
                    "<b>Оплату отримано</b>\n\n"
                    f"<b>Пакет:</b> {result.get('package_title', 'платний пакет')}\n"
                    f"<b>Додано перевірок:</b> {result['checks_added']}\n\n"
                    "Поточний баланс можна переглянути командою <code>/limits</code>."
                )

            await bot.send_message(
                chat_id=result["user_id"],
                text=success_text,
                parse_mode="HTML",
            )

            await notify_payment_credited(
                bot,
                user_id=result["user_id"],
                package_title=result.get("package_title", "платний пакет"),
                checks_added=result["checks_added"],
                sandbox=LIQPAY_SANDBOX,
            )
        finally:
            await bot.session.close()

    return {"status": "ok", "result": result}
