import datetime as dt

import pytest

from app import finance
from app.claim import ClaimInputs, ItemInput, build_claim
from test_claim import TODAY, load
from test_policy_evaluator import EMP, POLICY


def ready_claim():
    extracted, cls = load()
    one = [e for e in extracted if e.source_file.startswith("r05")]
    inputs = ClaimInputs(items={"r05_stationery.png": ItemInput(business_purpose="Office restock")})
    return build_claim(one, cls, EMP, POLICY, inputs, today=TODAY)


def test_ready_claim_is_stored_and_retrievable(tmp_path):
    db = tmp_path / "f.sqlite"
    claim = ready_claim()
    out = finance.submit_claim(db, claim, now=dt.datetime(2026, 10, 12, 10, 0))
    assert out["id"] == "RMB-20261012-0001"
    rows = finance.list_claims(db)
    assert rows[0]["employee_name"] == EMP.name and rows[0]["eligible_inr"] == claim.eligible_inr
    stored = finance.get_claim(db, out["id"])
    assert stored["payload"]["items"][0]["file"] == "r05_stationery.png"


def test_references_increment(tmp_path):
    db = tmp_path / "f.sqlite"
    a = finance.submit_claim(db, ready_claim(), now=dt.datetime(2026, 10, 12))
    b = finance.submit_claim(db, ready_claim(), now=dt.datetime(2026, 10, 12))
    assert (a["id"], b["id"]) == ("RMB-20261012-0001", "RMB-20261012-0002")


def test_claim_that_is_not_ready_is_refused(tmp_path):
    extracted, cls = load()
    claim = build_claim(extracted[:3], cls, EMP, POLICY, today=TODAY)
    with pytest.raises(finance.NotSubmittable):
        finance.submit_claim(tmp_path / "f.sqlite", claim)
    assert finance.list_claims(tmp_path / "f.sqlite") == []


def test_unknown_claim_returns_none(tmp_path):
    assert finance.get_claim(tmp_path / "f.sqlite", "nope") is None
