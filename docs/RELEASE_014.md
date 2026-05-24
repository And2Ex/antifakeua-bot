# AntiFakeUA Bot release 014

## Зміни

- Перехід із Telegram polling на Telegram webhook для Render Free.
- `/start` тепер може будити Render напряму через HTTP-запит від Telegram.
- LiqPay callback залишився на `/liqpay/callback`.
- Додано публічну HTML-сторінку на `/` для опису сервісу, контактів і правил повернення коштів.
- Додано `/healthz` для перевірки стану сервера.
- Повернуто команди `/buy` і `/limits` у приватне меню Telegram.

## Render

Start Command:

```bash
python run_webhook.py
```

Environment:

```env
BASE_WEBHOOK_URL=https://antifakeua-bot.onrender.com
PAYMENT_RESULT_URL=https://t.me/AntiFakeUA_Bot
```

## Важливо

Після деплою відкрий:

```text
https://antifakeua-bot.onrender.com/healthz
```

Потім напиши боту `/start`. Якщо Render спить, Telegram webhook має сам розбудити сервіс.
