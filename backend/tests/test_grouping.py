import datetime as dt

from app.grouping import group_by_date


def test_grouping_splits_on_gap_and_titles_ranges():
    d = dt.date
    groups = group_by_date([("a", d(2026, 9, 14)), ("b", d(2026, 9, 16)), ("c", d(2026, 9, 25)), ("d", d(2026, 9, 1))])
    assert [g.files for g in groups] == [["d"], ["a", "b"], ["c"]]
    assert groups[1].title == "Expenses 14 Sep – 16 Sep 2026"
    assert groups[0].title == "Expenses on 01 Sep 2026"
    assert groups[1].id == "g-2026-09-14"
