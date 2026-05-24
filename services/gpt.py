import json

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL


client = AsyncOpenAI(api_key=OPENAI_API_KEY)


FACT_CHECK_PROMPT = """
Ти — український фактчекер для Telegram-бота AntiFakeUA_Bot.

Завдання: перевірити текст новини, заяви або твердження українською мовою.

Використовуй web search. Не вигадуй фактів і не вигадуй джерел.

Визнач загальний verdict:
- Правда
- Фейк
- Маніпуляція
- Недостатньо даних
- Інше

Поле summary:
- дай короткий, зрозумілий висновок на 2-4 речення;
- це має бути відповідь на перевірку, а не довга стаття;
- якщо твердження правдиве — поясни, що саме підтверджується;
- якщо фейк — коротко перекажи або процитуй твердження і поясни, що саме неправдиве;
- якщо маніпуляція — поясни, що саме вводить в оману.

Поле blocks:
- використовуй тільки тоді, коли твердження складається з кількох різних частин;
- якщо твердження просте і його можна нормально пояснити в summary — поверни порожній список [];
- не дублюй summary у blocks;
- максимум 3 блоки.

Типи blocks:
- Правда
- Фейк
- Маніпуляція
- Уточнення
- Недостатньо даних

Поле sources:
- 0-5 джерел;
- тільки реальні URL;
- краще офіційні джерела, міжнародні агентства, авторитетні медіа;
- якщо джерел недостатньо — поверни менше джерел, але не вигадуй.

Якщо інформацію неможливо перевірити, verdict має бути "Недостатньо даних".
"""


FACT_CHECK_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": [
                "Правда",
                "Фейк",
                "Маніпуляція",
                "Недостатньо даних",
                "Інше"
            ]
        },
        "summary": {
            "type": "string"
        },
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "Правда",
                            "Фейк",
                            "Маніпуляція",
                            "Уточнення",
                            "Недостатньо даних"
                        ]
                    },
                    "text": {
                        "type": "string"
                    }
                },
                "required": ["type", "text"],
                "additionalProperties": False
            }
        },
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string"
                    },
                    "url": {
                        "type": "string"
                    }
                },
                "required": ["title", "url"],
                "additionalProperties": False
            }
        }
    },
    "required": ["verdict", "summary", "blocks", "sources"],
    "additionalProperties": False
}


async def analyze_text(text: str) -> dict:
    if not OPENAI_API_KEY:
        return build_error_result(
            "OPENAI_API_KEY не заданий у .env. Адміністратор має додати API-ключ."
        )

    try:
        response = await client.responses.create(
            model=OPENAI_MODEL,
            tools=[
                {
                    "type": "web_search_preview"
                }
            ],
            input=[
                {
                    "role": "developer",
                    "content": FACT_CHECK_PROMPT,
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "fact_check_result",
                    "strict": True,
                    "schema": FACT_CHECK_SCHEMA,
                }
            },
        )

        return json.loads(response.output_text)

    except Exception as error:
        print(f"GPT ERROR: {error}")

        return build_error_result(
            "Під час аналізу виникла технічна помилка. Спробуй повторити запит пізніше."
        )


def build_error_result(message: str) -> dict:
    return {
        "verdict": "Недостатньо даних",
        "summary": message,
        "blocks": [],
        "sources": [],
    }
