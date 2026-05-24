# Release 012 — Render polling fix

- `run_webhook.py` now uses the `PORT` environment variable provided by Render.
- FastAPI startup now initializes the database, registers routers, sets Telegram commands, and starts aiogram polling in the background.
- Added `/healthz` endpoint for Render health checks.
- This allows a single Render Web Service to handle both LiqPay callbacks and Telegram bot polling.

Important: do not run the local bot at the same time as the Render bot, otherwise Telegram polling may conflict.
