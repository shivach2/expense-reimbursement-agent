"""Deterministic post-extraction checks that decide if a receipt needs a human look."""

from __future__ import annotations

from app.currency import is_supported
from app.models import Receipt

MIN_CONFIDENCE = 0.7
SUM_TOLERANCE = 0.02  # 2% mismatch between line items (+tax) and total


def assess_receipt(r: Receipt) -> list[str]:
    if not r.readable:
        return ["Receipt is not readable"]

    reasons: list[str] = []
    if not r.vendor:
        reasons.append("Vendor name missing")
    if r.receipt_date is None:
        reasons.append("Date missing")
    if r.total is None:
        reasons.append("Total amount missing")

    present = {"vendor": r.vendor, "date": r.receipt_date, "total": r.total}
    for name, value in present.items():
        conf = getattr(r.confidence, name)
        if value is not None and conf < MIN_CONFIDENCE:
            reasons.append(f"Low confidence on {name} ({conf:.2f})")

    if not is_supported(r.currency):
        reasons.append(f"Unsupported currency {r.currency}")

    amounts = [i.amount for i in r.line_items if i.amount is not None]
    if r.total and amounts:
        # item prices may or may not already include tax; accept either reading
        with_tax = sum(amounts) + (r.tax or 0.0)
        candidates = (with_tax, sum(amounts))
        if all(abs(c - r.total) / r.total > SUM_TOLERANCE for c in candidates):
            reasons.append(f"Line items ({with_tax:.2f}) do not add up to total ({r.total:.2f})")

    return reasons
