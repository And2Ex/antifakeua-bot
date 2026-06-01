import re
from dataclasses import dataclass

from services.utils import normalize_text


@dataclass(frozen=True)
class NewsFilterDecision:
    eligible: bool
    reason: str


PROMOTION_PATTERNS = (
    r"\bреклам[аию]\b",
    r"\bпартнерськ(?:ий|а|е) матеріал\b",
    r"\bна правах реклами\b",
    r"\bпромокод\b",
    r"\bзнижк[аиу]\b",
    r"\bакці[яї]\b",
    r"\bкупуй(?:те)?\b",
    r"\bзамовляй(?:те)?\b",
    r"\bдоставк[аи]\b.{0,20}\bбезкоштовн",
    r"\bвід\s+\d+[\s.,]*(?:грн|₴|uah|usd|\$|євро|€)\b",
    r"#[а-яіїєґa-z_]*(?:реклама|promo|ad)\b",
)

NON_NEWS_PATTERNS = (
    r"^добрий\s+(?:ранок|день|вечір)",
    r"^віта(?:ємо|ю)",
    r"^друзі[!,. ]",
    r"^підписуй(?:те)?ся",
    r"^поставте\s+(?:лайк|реакц)",
    r"^голосуван",
)

FACT_SIGNAL_PATTERNS = (
    r"\b(?:повідомив|повідомила|заявив|заявила|оголосив|оголосила|підтвердив|підтвердила)\b",
    r"\b(?:відкрили|закрили|запустили|скасували|ухвалили|затримали|евакуювали|пошкоджено|зруйновано)\b",
    r"\b(?:сьогодні|вчора|завтра|цього\s+тижня|станом\s+на)\b",
    r"\b\d{1,2}[.\-/]\d{1,2}(?:[.\-/]\d{2,4})?\b",
    r"\b\d{4}\s+року\b",
    r"\b\d+[\s.,]*(?:осіб|людей|дітей|грн|млн|млрд|відсотк|%)\b",
    r"\b(?:місто|село|область|район|уряд|рада|міністерство|поліція|ова|дснс)\b",
)


def has_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def classify_channel_post(text: str | None) -> NewsFilterDecision:
    if not text:
        return NewsFilterDecision(False, "немає тексту")

    normalized = normalize_text(text)
    lowered = normalized.lower()
    words = normalized.split()

    if len(normalized) < 30 or len(words) < 5:
        return NewsFilterDecision(False, "замало тексту")

    if normalized.startswith("/"):
        return NewsFilterDecision(False, "службова команда")

    if "@antifakeua_bot" in lowered:
        return NewsFilterDecision(False, "власна позначка бота")

    if has_pattern(lowered, PROMOTION_PATTERNS):
        return NewsFilterDecision(False, "ознаки реклами або промоції")

    if has_pattern(lowered, NON_NEWS_PATTERNS):
        return NewsFilterDecision(False, "не новинний допис")

    if "?" in normalized and not has_pattern(lowered, FACT_SIGNAL_PATTERNS):
        return NewsFilterDecision(False, "питання без фактичного твердження")

    if has_pattern(lowered, FACT_SIGNAL_PATTERNS):
        return NewsFilterDecision(True, "є ознаки перевірюваної новини")

    if len(words) >= 16 and any(char.isdigit() for char in normalized):
        return NewsFilterDecision(True, "є зміст і числове твердження")

    return NewsFilterDecision(False, "не виявлено чіткого фактичного твердження")
