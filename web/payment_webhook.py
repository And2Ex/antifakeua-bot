import logging
from html import escape

from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from config import BASE_WEBHOOK_URL, BOT_USERNAME, GITHUB_URL, METHODOLOGY_URL, SUPPORT_JAR_URL


app = FastAPI(title="AntiFakeUA_Bot")
TELEGRAM_WEBHOOK_PATH = "/telegram/webhook"
LIQPAY_CALLBACK_PATH = "/liqpay/callback"


def render_homepage() -> str:
    bot_url = f"https://t.me/{BOT_USERNAME}"
    support_link = (
        f'<a class="button secondary" href="{escape(SUPPORT_JAR_URL, quote=True)}">Підтримати проєкт</a>'
        if SUPPORT_JAR_URL
        else ""
    )
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
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f5f7fb; color: #172033; line-height: 1.55; }}
    main {{ max-width: 860px; margin: 0 auto; padding: 40px 18px; }}
    .card {{ background: white; border-radius: 18px; padding: 26px; margin: 18px 0; box-shadow: 0 10px 30px rgba(20, 35, 70, 0.08); }}
    h1 {{ margin-top: 0; font-size: 34px; }}
    h2 {{ margin-bottom: 8px; }}
    a.button {{ display: inline-block; background: #1f6feb; color: white; text-decoration: none; padding: 12px 18px; border-radius: 12px; font-weight: bold; margin-right: 8px; margin-bottom: 8px; }}
    a.secondary {{ background: #172033; }}
    .muted {{ color: #5d6b82; }}
    ul {{ padding-left: 22px; }}
  </style>
</head>
<body>
<main>
  <section class="card">
    <h1>AntiFakeUA Bot</h1>
    <p><b>AntiFakeUA</b> — Telegram-бот для перевірки новин, заяв і пересланих повідомлень на ознаки фейків, маніпуляцій та непідтвердженої інформації.</p>
    <p><a class="button" href="{escape(bot_url, quote=True)}">Відкрити Telegram-бота</a>{support_link}</p>
  </section>

  <section class="card">
    <h2>Що робить бот</h2>
    <ul>
      <li>перевіряє текстові новини, заяви й переслані дописи;</li>
      <li>показує короткий вердикт, пояснення та джерела перевірки;</li>
      <li>дозволяє каналам підключати короткі автоматичні позначки під новинами;</li>
      <li>не ставить автоматичні позначки під рекламними повідомленнями.</li>
    </ul>
  </section>

  <section class="card">
    <h2>Підтримка проєкту</h2>
    <p>AntiFakeUA має безкоштовний ліміт перевірок. Проєкт можна добровільно підтримати через Monobank. Після підтвердження підтримки адміністратор може вручну надати додатковий ліміт перевірок.</p>
    <p class="muted">Скріншот переказу надсилається безпосередньо в боті через розділ підтримки.</p>
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
async def liqpay_callback_disabled():
    raise HTTPException(status_code=410, detail="Payment method is disabled")
