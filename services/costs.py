"""Credit and cost helpers.

Use credits for product limits, and estimated_cost_usd for internal accounting.
Prices are configurable because model pricing changes over time.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelPrice:
    input_per_1m: float
    output_per_1m: float


DEFAULT_MODEL_PRICES: dict[str, ModelPrice] = {
    # Update these from the official OpenAI pricing page when deploying.
    "gpt-4o-mini": ModelPrice(input_per_1m=0.15, output_per_1m=0.60),
    "gpt-4o": ModelPrice(input_per_1m=5.00, output_per_1m=15.00),
}


def estimate_openai_cost_usd(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    prices: dict[str, ModelPrice] | None = None,
) -> float:
    active_prices = prices or DEFAULT_MODEL_PRICES
    price = active_prices.get(model)
    if price is None:
        return 0.0

    input_cost = input_tokens / 1_000_000 * price.input_per_1m
    output_cost = output_tokens / 1_000_000 * price.output_per_1m
    return round(input_cost + output_cost, 6)


def credits_for_check(*, text_length: int, has_image: bool = False, deep_search: bool = False) -> int:
    credits = 1
    if text_length > 1200:
        credits += 1
    if text_length > 3500:
        credits += 1
    if has_image:
        credits += 2
    if deep_search:
        credits += 3
    return min(credits, 10)
