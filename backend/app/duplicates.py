"""Duplicate receipt detection.

Two layers: identical file bytes, and "same receipt" by content (vendor, date, amount).
Image hashing is deliberately not used: on same-template receipts different bills
hash identically and re-photographed copies hash far apart (measured on the
synthetic set), so it produces both false positives and false negatives.
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

VENDOR_SIMILARITY = 0.85
AMOUNT_TOLERANCE = 0.01


@dataclass(frozen=True)
class DupKey:
    file: str
    sha256: str
    vendor: str | None
    date: dt.date | None
    total: float | None
    currency: str
    receipt_number: str | None = None


@dataclass(frozen=True)
class DupMatch:
    original: str
    reason: str  # human-readable


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.casefold())


def _same_vendor(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio() >= VENDOR_SIMILARITY


def _same_receipt(a: DupKey, b: DupKey) -> bool:
    if None in (a.vendor, b.vendor, a.date, b.date, a.total, b.total):
        return False
    if a.date != b.date or a.currency != b.currency:
        return False
    if abs(a.total - b.total) > AMOUNT_TOLERANCE:
        return False
    if not _same_vendor(a.vendor, b.vendor):
        return False
    # Two different bill numbers mean two real purchases (e.g. two identical taxi fares).
    if a.receipt_number and b.receipt_number and _norm(a.receipt_number) != _norm(b.receipt_number):
        return False
    return True


def find_duplicates(keys: Sequence[DupKey], exempt: Collection[str] = ()) -> dict[str, DupMatch]:
    """Map duplicate file -> its original (the earliest earlier receipt).

    Files in `exempt` (the user said "not a duplicate") are never reported as duplicates
    but can still be the original that later receipts are compared against.
    """
    result: dict[str, DupMatch] = {}
    originals: list[DupKey] = []
    for key in keys:
        match: DupMatch | None = None
        if key.file not in exempt:
            for orig in originals:
                if orig.sha256 == key.sha256:
                    match = DupMatch(orig.file, "identical file")
                    break
                if _same_receipt(orig, key):
                    match = DupMatch(orig.file, "same vendor, date and amount")
                    break
        if match:
            result[key.file] = match
        else:
            originals.append(key)
    return result
