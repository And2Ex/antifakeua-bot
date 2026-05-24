# AntiFakeUA_Bot

Telegram-бот для прозорої перевірки новин, заяв і тверджень українською мовою.

## Можливості

- перевірка тексту через OpenAI Responses API;
- web search для пошуку джерел;
- структурована відповідь: вердикт, пояснення, блоки, джерела;
- кеш результатів;
- free-ліміти з автоматичним щомісячним оновленням;
- платний баланс перевірок через LiqPay;
- публічні перевірки через deep links;
- черга публікацій для адміна;
- публікація перевірок у Telegram-канал;
- статистика вердиктів, джерел і оплат;
- підтримка пересланих дописів, тексту, caption, reply у групах;
- прозорість: команда `/transparency`, відкритий prompt і підтримка GitHub-посилання.

## Встановлення

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Скопіюй `.env.example` у `.env` і заповни ключі.

```bash
python main.py
```

## Оплата LiqPay

У `.env` потрібно заповнити:

```env
LIQPAY_PUBLIC_KEY=
LIQPAY_PRIVATE_KEY=
LIQPAY_SANDBOX=1
BASE_WEBHOOK_URL=https://your-public-url.example
```

Для локального тестування webhook можна підняти через ngrok:

```bash
ngrok http 8000
```

Потім вставити HTTPS-адресу ngrok у `BASE_WEBHOOK_URL` і запустити webhook-сервер:

```bash
python run_webhook.py
```

Бот polling запускається окремо:

```bash
python main.py
```

Команда користувача:

```text
/buy
```

Після callback від LiqPay успішна оплата додає перевірки до `paid_balance`.

## Важливо

- Не публікуй `.env` у GitHub.
- Бот сам створить `antifake.db` при першому запуску.
- Для публікації в канал бот має бути адміном каналу з правом надсилати повідомлення.
- Для LiqPay webhook потрібна публічна HTTPS-адреса.


## Progress status

During a new fact-check the bot sends a silent progress message, updates it while the analysis is running, deletes it before the final result, and then sends the final answer as a normal notification. The timing is kept as UX constants in `handlers/check.py`, not in `.env`.

## Release 003: локальна аналітика

У проєкт додано легкий інфоаналіз без додаткових GPT-запитів:

- ознаки старої новини, поданої як нова;
- ознаки емоційної маніпуляції;
- виявлення доменів і Telegram-джерел;
- історія повторів через `content_history`;
- базова репутація джерел через `/source`;
- кешовані відповіді більше не списують ліміт.

