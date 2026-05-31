from services.utils import escape_html, truncate_text


def format_public_check(request) -> str:
    response_text = request["response_text"] or "Текст перевірки не збережено."
    request_text = truncate_text(request["request_text"], 1200)
    source_link = request["source_link"]

    parts = [
        "🔎 <b>Публічна перевірка AntiFakeUA</b>",
        f"<code>{escape_html(request['public_id'])}</code>",
        "",
        response_text,
    ]

    if source_link:
        parts.extend([
            "",
            f'📌 <a href="{escape_html(source_link)}">Оригінальний допис</a>',
        ])

    parts.extend([
        "",
        "<b>Перевірений текст:</b>",
        escape_html(request_text),
        "",
        "Перевірено через @AntiFakeUA_Bot",
    ])

    return "\n".join(parts).strip()
