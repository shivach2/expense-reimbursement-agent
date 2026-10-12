import datetime as dt

from app.currency import to_inr
from app.models import FieldConfidence, LineItem, Receipt
from app.quality import assess_receipt


def make(**over) -> Receipt:
    base = dict(
        readable=True,
        vendor="Bluebird Cafe",
        receipt_date=dt.date(2026, 9, 14),
        total=100.0,
        tax=0.0,
        currency="INR",
        category="meals",
        line_items=[],
        confidence=FieldConfidence(vendor=0.95, date=0.95, total=0.95),
    )
    base.update(over)
    return Receipt(**base)


def test_clean_receipt_has_no_reasons():
    assert assess_receipt(make()) == []


def test_unreadable_short_circuits():
    assert assess_receipt(make(readable=False)) == ["Receipt is not readable"]


def test_missing_fields_reported():
    reasons = assess_receipt(make(vendor=None, receipt_date=None, total=None))
    assert "Vendor name missing" in reasons
    assert "Date missing" in reasons
    assert "Total amount missing" in reasons


def test_low_confidence_flagged_only_when_value_present():
    low = FieldConfidence(vendor=0.95, date=0.2, total=0.4)
    reasons = assess_receipt(make(confidence=low))
    assert any("confidence on date" in r for r in reasons)
    assert any("confidence on total" in r for r in reasons)
    # absent date is reported as missing, not as low confidence
    reasons = assess_receipt(make(receipt_date=None, confidence=low))
    assert "Date missing" in reasons
    assert not any("confidence on date" in r for r in reasons)


def test_line_items_must_sum_to_total_with_or_without_tax():
    items = [LineItem(description="a", amount=60), LineItem(description="b", amount=40)]
    assert assess_receipt(make(line_items=items, total=100.0, tax=5.0)) == []  # items include tax
    assert assess_receipt(make(line_items=items, total=105.0, tax=5.0)) == []  # tax added on top
    reasons = assess_receipt(make(line_items=items, total=300.0, tax=5.0))
    assert any("do not add up" in r for r in reasons)


def test_unsupported_currency_flagged():
    assert any("Unsupported currency" in r for r in assess_receipt(make(currency="XYZ")))


def test_currency_normalised_and_validated():
    assert make(currency=" usd ").currency == "USD"
    try:
        make(currency="US")
    except ValueError:
        pass
    else:
        raise AssertionError("expected validation error")


def test_to_inr():
    assert to_inr(10, "USD") == 830.0
    assert to_inr(10, "inr") == 10.0
    assert to_inr(10, "XYZ") is None
