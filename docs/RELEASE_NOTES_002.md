# AntiFakeUA Bot — release addon 002

Цей пакет додає легкі функції, які не потребують додаткових вкладень і не витрачають токени до GPT-запиту.

## Додано

1. `services/lightweight_analysis.py`
   - витягування URL і доменів;
   - пошук ознак емоційної маніпуляції;
   - ризик “стара новина подана як нова”;
   - витягування основного твердження;
   - рекомендований режим перевірки;
   - кредитна оцінка перевірки.

2. `services/reputation.py`
   - створення джерел у БД;
   - оновлення статистики джерела після вердикту;
   - простий індекс надійності 0–100;
   - запис згадок джерел.

3. `services/costs.py`
   - оцінка вартості токенів;
   - credits для лімітів.

4. `database/migrations/002_lightweight_analytics.sql`
   - таблиці для checks, usage_logs, sources, source_mentions, content_history, tracked_events, watch_sources.

5. `handlers/analytics.py`
   - команда `/source`, яка показує репутацію джерела.

## Як інтегрувати

1. Скопіювати папки `services`, `database/migrations`, `scripts`, `handlers` у корінь проєкту.
2. Запустити міграцію:

```bash
python scripts/apply_lightweight_analytics_migration.py
```

3. У `setup_bot(dp)` додати:

```python
from handlers import analytics

dp.include_router(analytics.router)
```

4. Перед GPT-перевіркою можна додати:

```python
from services.lightweight_analysis import analyze_lightweight, format_lightweight_block

local_analysis = analyze_lightweight(user_text, has_image=False)
local_block = format_lightweight_block(local_analysis)
```

5. Після GPT-вердикту можна оновлювати джерело:

```python
import sqlite3
from config import DATABASE_PATH
from services.reputation import get_or_create_source, update_source_verdict

with sqlite3.connect(DATABASE_PATH) as conn:
    source_id = get_or_create_source(conn, name="example.com", url="https://example.com")
    update_source_verdict(conn, source_id=source_id, verdict="Фейк")
    conn.commit()
```

## Що це дає вже зараз

- бот починає накопичувати репутацію джерел;
- можна відстежувати старі новини, подані як нові;
- з’являється основа для платної аналітики;
- можна рахувати credits і собівартість;
- структура БД готова до майбутнього сайту й дашбордів.
