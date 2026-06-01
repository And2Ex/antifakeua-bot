import json

from services.formatter import format_fact_check_response
from services.utils import escape_html


def format_public_check(request) -> str:
    response_text = request["response_text"] or "Текст перевірки не збережено."
    raw_result = request.get("result_json")

    if raw_result:
        try:
            result = json.loads(raw_result)

            if isinstance(result, dict):
                response_text = format_fact_check_response(result)
        except (TypeError, json.JSONDecodeError):
            pass

    source_link = request["source_link"]
    parts = [response_text]

    if source_link:
        parts.extend([
            "",
            f'📌 <a href="{escape_html(source_link)}">Оригінальний допис</a>',
        ])

    return "\n".join(parts).strip()
