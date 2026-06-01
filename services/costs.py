"""Internal OpenAI API cost helpers for AntiFakeUA.

Rates below reflect Standard processing for the production fact-check model.
The application still uses one product credit per ordinary fact check; these
helpers are intended for internal cost reporting.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_1m: float
    output_per_1m: float


DEFAULT_MODEL_PRICES: dict[str, ModelPrice] = {
    # Standard processing prices from the OpenAI API pricing page, June 2026.
    "gpt-5.4-mini": ModelPrice(input_per_1m=0.75, output_per_1m=4.50),
}

WEB_SEARCH_COST_PER_CALL_USD = 10.00 / 1_000


def estimate_openai_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    web_search_calls: int = 0,
    prices: dict[str, ModelPrice] | None = None,
) -> float:
    active_prices = prices or DEFAULT_MODEL_PRICES
    price = active_prices.get(model)

    if price is None:
        return 0.0

    input_cost = max(input_tokens, 0) / 1_000_000 * price.input_per_1m
    output_cost = max(output_tokens, 0) / 1_000_000 * price.output_per_1m
    web_search_cost = max(web_search_calls, 0) * WEB_SEARCH_COST_PER_CALL_USD
    return round(input_cost + output_cost + web_search_cost, 6)


def credits_for_check(*, text_length: int, deep_search: bool = False) -> int:
    credits = 1

    if text_length > 1200:
        credits += 1

    if text_length > 3500:
        credits += 1

    if deep_search:
        credits += 3

    return min(credits, 10)
