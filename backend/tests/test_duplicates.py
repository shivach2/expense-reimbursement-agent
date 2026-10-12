import datetime as dt

from app.duplicates import DupKey, find_duplicates

D = dt.date(2026, 9, 14)


def key(file, *, sha=None, vendor="Bluebird Cafe", date=D, total=412.0, cur="INR", num=None):
    return DupKey(file, sha or f"sha-{file}", vendor, date, total, cur, num)


def test_identical_file_is_duplicate_even_without_extracted_fields():
    keys = [
        key("a.png", sha="same", vendor=None, date=None, total=None),
        key("b.png", sha="same", vendor=None, date=None, total=None),
    ]
    d = find_duplicates(keys)
    assert d["b.png"].original == "a.png"
    assert "a.png" not in d


def test_same_vendor_date_amount_is_duplicate():
    d = find_duplicates([key("a.png"), key("b.png")])
    assert d["b.png"].original == "a.png"


def test_vendor_spelling_variation_still_matches():
    d = find_duplicates([key("a.png", vendor="Bluebird Cafe"), key("b.png", vendor="BLUEBIRD CAFÉ.")])
    assert "b.png" in d


def test_different_amount_or_date_is_not_duplicate():
    assert find_duplicates([key("a.png"), key("b.png", total=413.0)]) == {}
    assert find_duplicates([key("a.png"), key("b.png", date=dt.date(2026, 9, 15))]) == {}
    assert find_duplicates([key("a.png"), key("b.png", cur="USD")]) == {}


def test_two_real_purchases_with_different_bill_numbers_are_kept():
    keys = [
        key("a.png", vendor="Zippy Cabs", total=410.0, num="5530"),
        key("b.png", vendor="Zippy Cabs", total=410.0, num="5531"),
    ]
    assert find_duplicates(keys) == {}


def test_same_bill_number_confirms_duplicate():
    keys = [key("a.png", num="4611"), key("b.png", num="4611")]
    assert "b.png" in find_duplicates(keys)


def test_missing_fields_never_match_semantically():
    keys = [key("a.png", date=None), key("b.png", date=None)]
    assert find_duplicates(keys) == {}


def test_exempt_item_is_kept_but_still_serves_as_original():
    keys = [key("a.png"), key("b.png"), key("c.png")]
    d = find_duplicates(keys, exempt={"b.png"})
    assert "b.png" not in d
    assert d["c.png"].original == "a.png"  # earliest original wins
