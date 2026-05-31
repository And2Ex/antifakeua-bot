# AntiFakeUA: запуск із Neon PostgreSQL та Render

Ця версія проєкту більше не використовує SQLite. Дані зберігаються у PostgreSQL на **Neon**, а Telegram webhook і LiqPay callback працюють через **Render Web Service**.

## Схема роботи

```text
Telegram / LiqPay
       ↓ HTTPS webhook
Render Web Service: AntiFakeUA_Bot
       ↓ DATABASE_URL
Neon PostgreSQL: постійні дані
```

У Neon зберігаються користувачі, ліміти, кеш перевірок, публічні ID, заявки на публікацію, платежі, джерела та статистика. Після restart або redeploy Render ці записи не повинні зникати.

---

## 1. Що вже змінено в коді

- `DATABASE_PATH` і SQLite прибрані з активного коду.
- Додано PostgreSQL-драйвер `psycopg`.
- База створюється з `database/schema.sql` при старті сервісу.
- Усі SQL-запити переведені на PostgreSQL.
- Формат відповіді тепер має короткий жирний заголовок одразу після вердикту.
- У prompt заборонено починати пояснення словами «Перевіряється твердження…».
- У проєкті немає `.db`, `__pycache__` і `.pyc` файлів.

---

## 2. Підготовка в PyCharm

### 2.1. Розпакування та відкриття

1. Розпакуй архів у папку, наприклад:

```text
C:\Users\V\PycharmProjects\AntiFakeUA_Bot
```

2. У PyCharm обери **File → Open** і відкрий цю папку.

### 2.2. Створення віртуального середовища

У терміналі PyCharm виконай:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Якщо PowerShell забороняє активацію середовища, у поточному вікні виконай:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2.3. Створення `.env`

У корені проєкту скопіюй `.env.example` у `.env`:

```powershell
Copy-Item .env.example .env
```

Поки що заповни відомі значення:

```env
BOT_TOKEN=...
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-mini
ADMIN_IDS=486192692
CHANNEL_ID=@AntiFakeUA
FREE_TEXT_LIMIT=30
LIQPAY_SANDBOX=1
```

`DATABASE_URL` додаси після створення Neon. Файл `.env` уже внесено до `.gitignore`, його не можна публікувати на GitHub.

---

## 3. Створення PostgreSQL-бази в Neon

### 3.1. Створити проєкт

1. Відкрий консоль Neon і зареєструйся або увійди.
2. Натисни **New Project**.
3. Назви проєкт, наприклад:

```text
antifakeua
```

4. Обери регіон, який зручний для твого Render-сервісу. Якщо в Render доступний Frankfurt, для Neon теж варто обрати європейський регіон поруч.
5. Створи проєкт. Neon одразу створить готову базу `neondb`.

### 3.2. Скопіювати рядок підключення

1. У проєкті Neon натисни **Connect**.
2. Обери **Python** або просто формат connection string.
3. Для цієї версії проєкту обери **Direct connection**, а не pooled: бот створює/перевіряє таблиці під час старту, а для ініціалізації схеми Neon рекомендує пряме підключення.
4. Скопіюй рядок підключення. Він виглядає приблизно так:

```env
DATABASE_URL=postgresql://USER:PASSWORD@ep-example.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

Важливо: параметр `sslmode=require` потрібно залишити. Не надсилай повний рядок підключення в чат і не коміть його у GitHub.

### 3.3. Підключити Neon локально

Встав скопійований рядок у локальний `.env`:

```env
DATABASE_URL=postgresql://...
```

Перевір з'єднання та створи таблиці:

```powershell
python -m scripts.test_database_connection
```

Правильний результат виглядає так:

```text
OK: connected to PostgreSQL.
Database: neondb
Server: PostgreSQL ...
```

### 3.4. Перевірити таблиці у Neon

У Neon відкрий **SQL Editor** і виконай:

```sql
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

У списку мають бути принаймні:

```text
users
requests
cache
payments
feedback
sources
content_history
app_settings
```

---

## 4. Локальна перевірка в PyCharm

Для швидкого тесту без webhook запусти polling-режим:

```powershell
python main.py
```

Перевір у Telegram:

1. Надішли боту конкретне твердження.
2. У відповіді має бути формат:

```text
✅ Правда

Жирний короткий заголовок про те, що саме підтверджено

Пояснення без фрази «Перевіряється твердження…»
```

3. Натисни **Публічна перевірка** — має відкритися збережений результат.
4. Зупини `main.py`, запусти знову і повторно відкрий те саме публічне посилання. Результат має залишитися, бо він уже в Neon.

Не запускай локальний polling одночасно з активним webhook на Render для одного й того самого бота: вони можуть конкурувати за Telegram updates.

---

## 5. Завантаження коду на GitHub через PyCharm

Якщо репозиторій уже підключений:

```powershell
git status
git add .
git commit -m "Migrate database to Neon PostgreSQL and update fact-check format"
git push
```

Перед `git add .` переконайся, що `.env` не потрапляє у список файлів:

```powershell
git status --short
```

У GitHub мають потрапити `.env.example`, `render.yaml`, `database/schema.sql` і код, але **не `.env`**.

---

## 6. Налаштування Render

### Варіант A: оновити наявний Render Web Service

Це найпростіший варіант, якщо в тебе вже є сервіс AntiFakeUA на Render.

1. Відкрий наявний сервіс у Render.
2. Переконайся, що він підключений до гілки GitHub, куди ти запушив оновлений проєкт.
3. У **Settings** перевір:

```text
Runtime: Python 3
Build Command: pip install -r requirements.txt
Start Command: python run_webhook.py
Health Check Path: /healthz
```

4. У **Environment** додай або зміни змінні:

```env
DATABASE_URL=<прямий Neon connection string>
BOT_TOKEN=<токен Telegram-бота>
OPENAI_API_KEY=<ключ OpenAI>
OPENAI_MODEL=gpt-5.4-mini
ADMIN_IDS=486192692
CHANNEL_ID=@AntiFakeUA
FREE_TEXT_LIMIT=30
GITHUB_URL=https://github.com/And2Ex/AntiFakeUA_Bot
METHODOLOGY_URL=https://github.com/And2Ex/AntiFakeUA_Bot/blob/main/METHODOLOGY.md
LIQPAY_PUBLIC_KEY=<ключ, якщо потрібна оплата>
LIQPAY_PRIVATE_KEY=<ключ, якщо потрібна оплата>
LIQPAY_SANDBOX=1
PAYMENT_RESULT_URL=https://t.me/AntiFakeUA_Bot
```

5. Render покаже адресу сервісу, наприклад:

```text
https://antifakeua-bot.onrender.com
```

Додай її як:

```env
BASE_WEBHOOK_URL=https://antifakeua-bot.onrender.com
```

Без `/` у кінці.

6. Натисни **Save, rebuild, and deploy**.

### Варіант B: створити новий Web Service через `render.yaml`

У корені проєкту вже є `render.yaml`. У Render можна створити **Blueprint**, під'єднати GitHub-репозиторій і вручну ввести секретні змінні, позначені як `sync: false`.

Для першого переходу рекомендую **варіант A**, бо він не створить другого бота паралельно з наявним.

---

## 7. Перевірка роботи на Render

Після успішного деплою:

### 7.1. Перевірити сайт і health check

Відкрий у браузері:

```text
https://твій-сервіс.onrender.com/
https://твій-сервіс.onrender.com/healthz
```

Друга адреса має показати:

```json
{"status":"ok"}
```

### 7.2. Перевірити webhook Telegram

У Render → **Logs** має бути повідомлення про встановлення Telegram webhook на адресу виду:

```text
https://твій-сервіс.onrender.com/telegram/webhook
```

Після цього напиши боту в Telegram. Він має відповісти без запуску `main.py` на твоєму комп'ютері.

### 7.3. Перевірити, що дані більше не зникають

1. Перевір будь-яку новину через бота.
2. Натисни **Публічна перевірка** — вона має відкриватися.
3. У Render натисни **Manual Deploy → Deploy latest commit** або перезапусти сервіс.
4. Після деплою знову відкрий те саме публічне посилання.
5. Перевір `/start`: бот не повинен знову визначати тебе як нового користувача.

Якщо обидві перевірки проходять, SQLite-проблема усунена: дані вже зберігаються в Neon.

---

## 8. Що робити зі старою SQLite-базою

У переданому архіві немає файлу `.db`, тому автоматично переносити старі записи немає з чого. Якщо у тебе локально залишився справжній файл старої бази, наприклад `antifake.db`, не видаляй його. Його можна окремо імпортувати в Neon, якщо в ньому є важливі перевірки або користувачі.

На Render старий SQLite-файл не варто вважати надійним джерелом: після перезапусків у ньому могли вже зникнути актуальні записи.

---

## 9. Типові помилки

### `DATABASE_URL не заданий`

У `.env` локально або в Render Environment немає рядка Neon. Додай `DATABASE_URL` і перезапусти сервіс.

### `password authentication failed`

Рядок підключення скопійовано не повністю або пароль/роль було змінено в Neon. Скопіюй новий рядок через **Connect**.

### `relation "users" does not exist`

Таблиці не ініціалізувались. Локально виконай:

```powershell
python -m scripts.test_database_connection
```

або передеплой Render: при старті `init_db()` створює таблиці автоматично.

### Бот не відповідає після Render deploy

Перевір:

- `BASE_WEBHOOK_URL` дорівнює публічній HTTPS-адресі саме цього Render Web Service;
- у Render Logs є повідомлення про встановлення webhook;
- локальний `python main.py` вимкнений;
- `BOT_TOKEN` правильний.

### Публічна перевірка все ще не знаходиться

У Neon SQL Editor виконай:

```sql
SELECT public_id, verdict, created_at
FROM requests
ORDER BY created_at DESC
LIMIT 10;
```

Якщо рядок є, проблема в параметрі посилання або коді `/start`. Якщо рядка немає — сервіс використовує інший `DATABASE_URL` або запис не був створений.

---

## 10. Офіційна документація

- Neon Python guide: `https://neon.com/docs/guides/python`
- Neon secure connections: `https://neon.com/docs/connect/connect-securely`
- Neon pricing: `https://neon.com/pricing`
- Render Web Services: `https://render.com/docs/web-services`
- Render Environment Variables: `https://render.com/docs/configure-environment-variables`
- Render Free limitations: `https://render.com/docs/free`
