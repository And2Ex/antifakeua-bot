import json

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL


client = AsyncOpenAI(api_key=OPENAI_API_KEY)


PUBLICATION_PROMPT = """
Ти — редактор українського каналу AntiFakeUA. Твоя задача — підготувати окремий допис для публікації в каналі на основі вже виконаного фактчеку.

Ти НЕ виконуєш нову перевірку і НЕ додаєш нових фактів. Використовуй лише факти, які підтверджені в переданому результаті перевірки, та безпечний контекст з оригінального тексту, що прямо не суперечить перевірці.

Допис буде показаний адміністратору як чернетка перед публікацією.

Правила для verdict = "Правда":
1. Пиши як звичайну новину: одразу повідом суть події.
2. Не починай текст словами "справді", "підтверджено", "перевірка показала", "у дописі стверджується" або подібними формулюваннями.
3. Не пояснюй у тексті новини, що інші медіа це підтвердили. Для цього окремо будуть додані джерела перевірки.
4. Якщо перевірено лише частину великого оригінального допису, включай лише підтверджені факти; не переказуй непідтверджені деталі як встановлені.

Правила для verdict = "Маніпуляція" або "Фейк":
1. Заголовок має чітко відображати, що повідомлення вводить в оману або є неправдивим.
2. У тексті коротко назви поширене твердження та відразу наведи встановлений коректний контекст.
3. Не подавай спростоване твердження як новину без пояснення.

Загальні правила:
- Українська мова.
- Нейтральний, новинний стиль без емоцій і закликів.
- title: короткий самодостатній заголовок, без емодзі та без крапки в кінці.
- body: 1–3 короткі абзаци, максимум 850 символів; без заголовка, без вердикту, без блоку джерел і без посилань.
- Не вигадуй цитат, посад, дат, подій, причин або деталей.
- Не згадуй AntiFakeUA чи процес перевірки в body.
"""


PUBLICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["title", "body"],
    "additionalProperties": False,
}


async def generate_publication_draft(request: dict, fact_check: dict) -> dict:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY не заданий у .env")

    payload = {
        "original_text": request.get("request_text", ""),
        "original_source_title": request.get("source_title", ""),
        "verdict": fact_check.get("verdict", "Недостатньо даних"),
        "verified_summary": fact_check.get("summary", ""),
        "verified_details": fact_check.get("blocks", []),
        "verification_sources": fact_check.get("sources", []),
    }

    try:
        response = await client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "developer", "content": PUBLICATION_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "publication_draft",
                    "strict": True,
                    "schema": PUBLICATION_SCHEMA,
                }
            },
        )

        result = json.loads(response.output_text)
        title = str(result.get("title", "")).strip()
        body = str(result.get("body", "")).strip()

        if not title or not body:
            raise ValueError("GPT повернув порожню чернетку допису")

        return {"title": title, "body": body}

    except Exception as error:
        print(f"PUBLICATION GPT ERROR: {error}")
        raise RuntimeError("Не вдалося сформувати новинний допис. Спробуй ще раз.") from error
