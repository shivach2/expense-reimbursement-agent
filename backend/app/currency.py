"""Static, illustrative FX rates to INR (prototype only, not live market data)."""

from __future__ import annotations

RATES_TO_INR: dict[str, float] = {
    "INR": 1.0,
    "USD": 83.0,
    "EUR": 90.0,
    "GBP": 105.0,
    "SGD": 62.0,
    "AED": 22.6,
}


def is_supported(currency: str) -> bool:
    return currency.upper() in RATES_TO_INR


def to_inr(amount: float, currency: str) -> float | None:
    rate = RATES_TO_INR.get(currency.upper())
    return None if rate is None else round(amount * rate, 2)
