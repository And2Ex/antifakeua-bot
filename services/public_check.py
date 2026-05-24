from services.utils import escape_html, truncate_text


def format_public_check(request) -> str:
    verdict = request["verdict"] or "Недостатньо даних"
    response_text = request["response_text"] or "Текст перевірки не збережено."
    request_text = truncate_text(request["request_text"], 1200)
    source_link = request["source_link"]

    parts = [
        "🔎 <b>Публічна перевірка AntiFakeUA</b>",
        "",
        f"<b>Код перевірки:</b> <code>{escape_html(request['public_id'])}</code>",
        f"<b>Підсумок:</b> {escape_html(verdict)}",
    ]

    if source_link:
        parts.append(f'📌 <a href="{escape_html(source_link)}">Оригінальний допис</a>')

    parts.extend([
        "",
        "<b>Що перевіряли:</b>",
        escape_html(request_text),
        "",
        response_text,
        "",
        "Цю перевірку можна переслати іншим — вона відкриється через цей самий код без повторного аналізу.",
        "Перевірено через @AntiFakeUA_Bot",
    ])

    return "\n".join(parts).strip()
