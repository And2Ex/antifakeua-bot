from database.db import get_cache, save_cache
from services.utils import generate_text_hash


def get_cached_response(text: str):
    text_hash = generate_text_hash(text)

    return get_cache(text_hash)


def save_cached_response(text: str, response: str, verdict: str | None = None):
    text_hash = generate_text_hash(text)

    save_cache(
        text_hash=text_hash,
        original_text=text,
        response_text=response,
        verdict=verdict
    )
