from services.utils import escape_html


def format_public_check(request) -> str:
    response_text = request["response_text"] or "Текст перевірки не збережено."
    source_link = request["source_link"]
    parts = [response_text]

    if source_link:
        parts.extend([
            "",
            f'📌 <a href="{escape_html(source_link)}">Оригінальний допис</a>',
        ])

    return "\n".join(parts).strip()
