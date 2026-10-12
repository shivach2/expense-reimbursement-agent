# A2 — verbatim source: backend tests

Create every file below at the given path with **exactly** the content between the fences (the fence lines themselves are not part of the file). Each file ends with a single trailing newline. Do not change anything. Create missing folders as needed. A file marked `(empty file)` must be created empty. Some fences are four backticks long because the file itself contains three-backtick code blocks; the fence that closes a file has the same length as the one that opened it.

### FILE: backend/pytest.ini  (3 lines)

```ini
[pytest]
pythonpath = .
testpaths = tests
```

### FILE: backend/tests/factories.py  (33 lines)

```python
"""Shared builders for tests that need an AppState or a Session without calling any LLM."""

from __future__ import annotations

from app.classifier import Classification
from app.config import get_settings
from app.models import ExtractedReceipt
from app.state import AppState, Session
from test_claim import TODAY, load
from test_policy_evaluator import POLICY


def make_state(tmp_path, policy=POLICY) -> AppState:
    """An AppState with the fixture policy preloaded, so nothing needs the LLM or the policy cache."""
    state = AppState(get_settings(), runtime_dir=tmp_path, today=TODAY)
    state._policy = policy
    return state


def truth_for(*prefixes: str) -> tuple[list[ExtractedReceipt], dict[str, Classification]]:
    """Ground-truth extraction + classification for the synthetic receipts whose file name starts with a prefix."""
    extracted, classifications = load()
    keep = [e for e in extracted if e.source_file.startswith(prefixes)]
    return keep, {e.source_file: classifications[e.source_file] for e in keep}


def session_with(state: AppState, *prefixes: str) -> Session:
    """A ready session holding the chosen synthetic receipts and a built claim."""
    s = state.create_session()
    s.extracted, s.classifications = truth_for(*prefixes)
    state.rebuild(s)
    s.status = "ready"
    return s
```

### FILE: backend/tests/test_ingest.py  (58 lines)

```python
import io

import pytest
from PIL import Image

from app.ingest import UnsupportedFileError, load_bytes


def _png(size=(3000, 1000)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


def test_image_is_downscaled_and_reencoded_as_jpeg():
    loaded = load_bytes(_png(), "a.png", max_side=1600)
    page = loaded.pages[0]
    assert page.media_type == "image/jpeg"
    assert max(Image.open(io.BytesIO(page.data)).size) <= 1600
    assert len(loaded.sha256) == 64


def test_exif_metadata_is_stripped():
    exif = Image.Exif()
    exif[0x010F] = "TestCam"  # Make
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, "JPEG", exif=exif)
    assert Image.open(io.BytesIO(buf.getvalue())).getexif()  # sanity: input has EXIF

    loaded = load_bytes(buf.getvalue(), "a.jpg")
    assert not Image.open(io.BytesIO(loaded.pages[0].data)).getexif()


def test_pdf_is_rasterised():
    buf = io.BytesIO()
    Image.new("RGB", (400, 600), "white").save(buf, "PDF")
    loaded = load_bytes(buf.getvalue(), "r.pdf")
    assert len(loaded.pages) == 1
    assert loaded.pages[0].media_type == "image/jpeg"


def test_same_bytes_same_hash():
    assert load_bytes(_png(), "a.png").sha256 == load_bytes(_png(), "b.png").sha256


def test_unsupported_extension_rejected():
    with pytest.raises(UnsupportedFileError):
        load_bytes(b"hello", "notes.txt")


def test_corrupt_image_rejected():
    with pytest.raises(UnsupportedFileError):
        load_bytes(b"not an image", "a.png")


def test_corrupt_pdf_rejected():
    with pytest.raises(UnsupportedFileError):
        load_bytes(b"not a pdf", "a.pdf")
```

### FILE: backend/tests/test_quality.py  (75 lines)

```python
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
```

### FILE: backend/tests/test_extraction.py  (148 lines)

```python
import asyncio
import io
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.config import Settings
from app.extraction import build_agent, extract_receipt

GOOD = {
    "readable": True,
    "vendor": "Bluebird Cafe",
    "receipt_date": "2026-09-14",
    "total": 412.0,
    "tax": 19.62,
    "currency": "inr",
    "category": "meals",
    "line_items": [],
    "confidence": {"vendor": 0.9, "date": 0.9, "total": 0.9},
}


@pytest.fixture
def receipt_file(tmp_path):
    p = tmp_path / "secret_scenario_name.png"
    buf = io.BytesIO()
    Image.new("RGB", (200, 300), "white").save(buf, "PNG")
    p.write_bytes(buf.getvalue())
    return p


@pytest.fixture
def settings(tmp_path):
    return Settings(
        llm_model="test:model",
        llm_call_delay_s=0,
        use_extraction_cache=False,
        cache_dir=tmp_path / "cache",
    )


def run(coro):
    return asyncio.run(coro)


def test_successful_extraction_normalises_and_caches(receipt_file, settings):
    agent = build_agent(TestModel(custom_output_args=GOOD))
    result = run(extract_receipt(receipt_file, agent=agent, settings=settings))

    assert result.error is None
    assert result.receipt.currency == "INR"
    assert result.total_inr == 412.0
    assert result.needs_review is False
    assert len(list(settings.cache_dir.rglob("*.json"))) == 1


def test_foreign_currency_converted(receipt_file, settings):
    agent = build_agent(TestModel(custom_output_args={**GOOD, "currency": "USD", "total": 10.0}))
    result = run(extract_receipt(receipt_file, agent=agent, settings=settings))
    assert result.total_inr == 830.0


def test_cache_hit_skips_the_llm(receipt_file, settings):
    agent = build_agent(TestModel(custom_output_args=GOOD))
    first = run(extract_receipt(receipt_file, agent=agent, settings=settings))

    class Boom:
        async def run(self, *a, **k):
            raise AssertionError("LLM must not be called on cache hit")

    cached_settings = replace(settings, use_extraction_cache=True)
    again = run(extract_receipt(receipt_file, agent=Boom(), settings=cached_settings))
    assert again.receipt == first.receipt


def test_persistent_invalid_output_returns_error_result(receipt_file, settings):
    def bad(messages, info: AgentInfo):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"currency": "??"})])

    agent = build_agent(FunctionModel(bad))
    result = run(extract_receipt(receipt_file, agent=agent, settings=settings))

    assert result.receipt is None
    assert result.needs_review is True
    assert result.error
    assert not list(settings.cache_dir.rglob("*.json"))  # failures are not cached


def test_file_name_is_not_sent_to_the_model(receipt_file, settings):
    seen: list[str] = []

    def spy(messages, info: AgentInfo):
        seen.append(str(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, GOOD)])

    run(extract_receipt(receipt_file, agent=build_agent(FunctionModel(spy)), settings=settings))
    assert seen and "secret_scenario_name" not in seen[0]


def test_rate_limit_is_retried(receipt_file, settings, monkeypatch):
    calls = {"n": 0}

    class Flaky:
        async def run(self, content):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ModelHTTPError(429, "test", body=None)
            from app.models import Receipt

            return SimpleNamespace(output=Receipt.model_validate(GOOD))

    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.extraction.asyncio.sleep", no_sleep)
    result = run(extract_receipt(receipt_file, agent=Flaky(), settings=settings))
    assert calls["n"] == 2
    assert result.error is None


def test_daily_quota_is_not_retried(receipt_file, settings):
    calls = {"n": 0}

    class OutOfQuota:
        async def run(self, content):
            calls["n"] += 1
            raise ModelHTTPError(
                429, "test", body={"error": {"message": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}}
            )

    with pytest.raises(ModelHTTPError):
        run(extract_receipt(receipt_file, agent=OutOfQuota(), settings=settings))
    assert calls["n"] == 1


def test_non_retryable_http_error_propagates(receipt_file, settings):
    class Unauthorized:
        async def run(self, content):
            raise ModelHTTPError(401, "test", body=None)

    with pytest.raises(ModelHTTPError):
        run(extract_receipt(receipt_file, agent=Unauthorized(), settings=settings))
```

### FILE: backend/tests/test_duplicates.py  (60 lines)

```python
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
```

### FILE: backend/tests/test_grouping.py  (12 lines)

```python
import datetime as dt

from app.grouping import group_by_date


def test_grouping_splits_on_gap_and_titles_ranges():
    d = dt.date
    groups = group_by_date([("a", d(2026, 9, 14)), ("b", d(2026, 9, 16)), ("c", d(2026, 9, 25)), ("d", d(2026, 9, 1))])
    assert [g.files for g in groups] == [["d"], ["a", "b"], ["c"]]
    assert groups[1].title == "Expenses 14 Sep – 16 Sep 2026"
    assert groups[0].title == "Expenses on 01 Sep 2026"
    assert groups[1].id == "g-2026-09-14"
```

### FILE: backend/tests/test_policy_evaluator.py  (272 lines)

```python
"""Evaluator tests. POLICY is a hand-written stand-in for what the LLM interpreter extracts from
data/policies/*.md; test_policy_interpreter checks every item in it is verbatim-grounded in those files."""

import datetime as dt

import pytest

from app.policy.evaluator import Outcome, UsageTracker, evaluate_line
from app.policy.schema import (
    AgeRule,
    CategoryDef,
    Employee,
    Entitlement,
    Exclusion,
    Limit,
    PolicyConstraints,
    PolicySet,
)

TEP, GE = "travel_expense_policy.md", "grade_entitlements.md"
EXEC, MGR, DIR = ["E1", "E2", "E3"], ["M1", "M2", "M3"], ["D1", "D2", "D3"]
BASE = ["meals", "local_transport", "fuel", "communication", "office_supplies", "training"]
LABELS = {
    "meals": "Meals",
    "local_transport": "Local transport",
    "fuel": "Fuel",
    "communication": "Communication",
    "office_supplies": "Office supplies",
    "training": "Training",
    "lodging": "Lodging",
    "client_entertainment": "Client entertainment",
    "personal_expenses": "Personal expenses",
}


def _lim(doc, clause, quote, cat, amount, unit, action, grades=None, approval=False):
    return Limit(
        document=doc,
        clause=clause,
        quote=quote,
        category=cat,
        amount=amount,
        unit=unit,
        over_limit_action=action,
        grades=grades,
        requires_approval=approval,
    )


def make_policy(hotel_cap: float = 5000) -> PolicySet:
    cats = [CategoryDef(id=k, label=v, description=v) for k, v in LABELS.items()]
    ent = []
    for clause, grades, extra, quote in [
        (
            "2.1",
            EXEC,
            [],
            "Executive grades are eligible to claim meals, local transport, fuel, communication, office supplies and training.",
        ),
        (
            "2.2",
            MGR,
            ["lodging", "client_entertainment"],
            "Manager grades are eligible to claim everything available to Executive grades, and additionally lodging and client entertainment.",
        ),
        (
            "2.3",
            DIR,
            ["lodging", "client_entertainment"],
            "Director grades are eligible to claim every category available to Manager grades.",
        ),
    ]:
        for cat in BASE + extra:
            ent.append(Entitlement(document=GE, clause=clause, quote=quote, category=cat, grades=grades))
    hotel_quote = "Hotel accommodation is reimbursable up to INR 5,000 per night."
    limits = [
        _lim(TEP, "2.1", hotel_quote, "lodging", hotel_cap, "per_night", "partial"),
        _lim(
            TEP,
            "3.1",
            "Meals during business travel are reimbursable up to INR 1,500 per receipt.",
            "meals",
            1500,
            "per_receipt",
            "needs_approval",
        ),
        _lim(
            TEP,
            "4.1",
            "Local taxi, cab, parking and public transport are reimbursable up to INR 3,000 per day.",
            "local_transport",
            3000,
            "per_day",
            "reject",
        ),
        _lim(
            TEP,
            "4.2",
            "Fuel for a personal vehicle used on official duty is reimbursable up to INR 2,500 per receipt.",
            "fuel",
            2500,
            "per_receipt",
            "reject",
        ),
        _lim(
            TEP,
            "5.1",
            "Meals and entertainment for clients are reimbursable up to INR 3,000 per receipt.",
            "client_entertainment",
            3000,
            "per_receipt",
            "reject",
        ),
        _lim(
            TEP,
            "6.1",
            "Training courses and conference fees are reimbursable up to INR 15,000 per receipt, and require prior written approval from the employee's manager.",
            "training",
            15000,
            "per_receipt",
            "reject",
            approval=True,
        ),
        _lim(
            TEP,
            "7.1",
            "Office supplies are reimbursable up to INR 1,000 per receipt.",
            "office_supplies",
            1000,
            "per_receipt",
            "reject",
        ),
        _lim(
            GE,
            "3.1",
            "Mobile and broadband bills are reimbursable up to INR 800 per month for Executive grades.",
            "communication",
            800,
            "per_month",
            "reject",
            grades=EXEC,
        ),
        _lim(
            GE,
            "3.2",
            "Mobile and broadband bills are reimbursable up to INR 1,200 per month for Manager and Director grades.",
            "communication",
            1200,
            "per_month",
            "reject",
            grades=MGR + DIR,
        ),
    ]
    excl = [
        Exclusion(
            document=TEP,
            clause="1.3",
            category="personal_expenses",
            reason="personal, medical, fine and penalty expenses are never reimbursable",
            quote="Personal expenses, medical expenses, fines and penalties are not reimbursable under any circumstances.",
        )
    ]
    age = [
        AgeRule(document=TEP, clause="1.1", quote="Receipts older than 60 days are not reimbursable.", max_age_days=60)
    ]
    c = PolicyConstraints(categories=cats, entitlements=ent, limits=limits, exclusions=excl, age_rules=age)
    return PolicySet.merge([(TEP, "sha-tep", c)])


POLICY = make_policy()
EMP = Employee(id="E-1", name="Test (synthetic)", grade="M2", role="Manager", base_city="Pune")
TODAY = dt.date(2026, 10, 9)
D = dt.date(2026, 9, 18)


def ev(category, amount, *, emp=EMP, policy=POLICY, date=D, tracker=None, **kw):
    return evaluate_line(
        category=category,
        claimed_inr=amount,
        date=date,
        employee=emp,
        policy=policy,
        today=TODAY,
        tracker=tracker or UsageTracker(),
        **kw,
    )


def test_hotel_over_cap_is_partially_reimbursed_with_clause_and_quote():
    d = ev("lodging", 6000)
    assert d.outcome is Outcome.PARTIAL
    assert d.eligible_inr == 5000
    assert d.cites[-1].ref == "TEP-2.1" and "INR 5,000 per night" in d.cites[-1].quote
    assert "INR 1,000" in d.explanation and "TEP-2.1" in d.explanation


def test_hotel_within_cap_and_multi_night():
    assert ev("lodging", 4000).outcome is Outcome.APPROVED
    d = ev("lodging", 9000, nights=2)
    assert d.outcome is Outcome.APPROVED and d.eligible_inr == 9000


def test_policy_change_applies_without_code_change():
    assert ev("lodging", 6000).eligible_inr == 5000
    assert ev("lodging", 6000, policy=make_policy(hotel_cap=7000)).outcome is Outcome.APPROVED


def test_meals_over_cap_needs_exception_then_approved_with_justification():
    d = ev("meals", 2000)
    assert d.outcome is Outcome.FLAGGED and d.eligible_inr == 0 and d.needs
    d = ev("meals", 2000, justification="Client dinner, manager approved")
    assert d.outcome is Outcome.APPROVED and d.eligible_inr == 2000


def test_excluded_category_rejected_with_clause():
    d = ev("personal_expenses", 300)
    assert d.outcome is Outcome.REJECTED and d.cites[0].ref == "TEP-1.3"


def test_grade_not_entitled():
    exec_emp = EMP.model_copy(update={"grade": "E2"})
    d = ev("lodging", 3000, emp=exec_emp)
    assert d.outcome is Outcome.REJECTED and "E2" in d.explanation and d.cites[0].ref == "GE-2.2"


def test_receipt_age_limit_boundary():
    assert ev("meals", 500, date=TODAY - dt.timedelta(days=60)).outcome is Outcome.APPROVED
    d = ev("meals", 500, date=TODAY - dt.timedelta(days=61))
    assert d.outcome is Outcome.REJECTED and d.cites[0].ref == "TEP-1.1"


def test_missing_date_skips_age_check():
    assert ev("meals", 500, date=None).outcome is Outcome.APPROVED


def test_per_day_limit_is_shared_across_receipts_on_same_day():
    t = UsageTracker()
    assert ev("local_transport", 2000, tracker=t).outcome is Outcome.APPROVED
    assert ev("local_transport", 2000, tracker=t).outcome is Outcome.REJECTED  # only 1,000 left that day
    assert ev("local_transport", 2000, tracker=t, date=D + dt.timedelta(days=1)).outcome is Outcome.APPROVED


def test_grade_specific_limit_beats_general_and_is_monthly():
    assert ev("communication", 1178.82).outcome is Outcome.APPROVED  # manager: 1,200
    assert (
        ev("communication", 1178.82, emp=EMP.model_copy(update={"grade": "E2"})).outcome is Outcome.REJECTED
    )  # exec: 800
    t = UsageTracker()
    assert ev("communication", 700, tracker=t).outcome is Outcome.APPROVED
    assert ev("communication", 700, tracker=t).outcome is Outcome.REJECTED  # 500 left this month


def test_training_requires_prior_approval_even_under_limit():
    d = ev("training", 11210)
    assert d.outcome is Outcome.FLAGGED and "approval" in d.needs[0]
    assert ev("training", 11210, justification="Approved by manager, ref 123").outcome is Outcome.APPROVED


def test_unknown_category_is_flagged_for_clarification():
    d = ev("spaceships", 10)
    assert d.outcome is Outcome.FLAGGED and d.needs == ["category"]


def test_eligible_categories_depend_on_grade():
    assert "lodging" in POLICY.eligible_categories("M2")
    assert "lodging" not in POLICY.eligible_categories("E1")
    assert "personal_expenses" not in POLICY.eligible_categories("M2")


@pytest.mark.parametrize("amount", [0.0, 0.01])
def test_tiny_amounts_are_fine(amount):
    assert ev("meals", amount).outcome is Outcome.APPROVED
```

### FILE: backend/tests/test_policy_interpreter.py  (185 lines)

```python
import asyncio
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.config import Settings
from app.policy.clauses import ClauseIndex, load_documents, parse_clauses
from app.policy.interpreter import (
    PolicyInterpretationError,
    build_interpreter_agent,
    grounding_problems,
    interpret_document,
    load_policy_set,
)
from app.policy.schema import PolicyConstraints
from test_policy_evaluator import GE, POLICY, TEP, make_policy

POLICY_DIR = Path(__file__).resolve().parents[2] / "data" / "policies"
DOCS = load_documents(POLICY_DIR)


def part(doc: str, policy=POLICY) -> PolicyConstraints:
    """The slice of the fixture that came from one document."""
    f = lambda items: [i for i in items if i.document == doc]  # noqa: E731
    return PolicyConstraints(
        categories=policy.categories,
        entitlements=f(policy.entitlements),
        limits=f(policy.limits),
        exclusions=f(policy.exclusions),
        age_rules=f(policy.age_rules),
    )


def clauses_of(doc: str) -> dict[str, str]:
    return {c.number: c.text for c in parse_clauses(doc, DOCS[doc])}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        llm_model="test:m",
        llm_call_delay_s=0,
        use_extraction_cache=False,
        cache_dir=tmp_path / "x",
        policy_cache_dir=tmp_path / "policy",
    )


def canned(responses: dict[str, PolicyConstraints], calls: list | None = None):
    """FunctionModel that answers with the constraints for whichever document is in the prompt."""

    def fn(messages, info: AgentInfo):
        text = str(messages)
        if calls is not None:
            calls.append(text)
        doc = next(d for d in responses if f"Document file name: {d}" in text)
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, responses[doc].model_dump(mode="json"))])

    return FunctionModel(fn)


# ---- the hand-written fixture must be genuinely grounded in the real documents ----
@pytest.mark.parametrize("doc", [TEP, GE])
def test_fixture_is_verbatim_grounded_in_real_documents(doc):
    assert grounding_problems(part(doc), clauses_of(doc)) == []


# ---- grounding checks ----
def test_grounding_catches_each_kind_of_hallucination():
    base = part(TEP)
    clauses = clauses_of(TEP)

    wrong_amount = base.model_copy(deep=True)
    wrong_amount.limits[0].amount = 9999
    assert any("does not appear in the quote" in p for p in grounding_problems(wrong_amount, clauses))

    bad_quote = base.model_copy(deep=True)
    bad_quote.limits[0].quote = "Hotels are reimbursable up to INR 5,000 per night."
    assert any("verbatim" in p for p in grounding_problems(bad_quote, clauses))

    bad_clause = base.model_copy(deep=True)
    bad_clause.limits[0].clause = "9.9"
    assert any("does not exist" in p for p in grounding_problems(bad_clause, clauses))

    bad_cat = base.model_copy(deep=True)
    bad_cat.limits[0].category = "yachts"
    assert any("not in `categories`" in p for p in grounding_problems(bad_cat, clauses))

    wrong_age = base.model_copy(deep=True)
    wrong_age.age_rules[0].max_age_days = 90
    assert any("age rule" in p for p in grounding_problems(wrong_age, clauses))


def test_quote_matching_ignores_whitespace_and_case():
    c = part(TEP).model_copy(deep=True)
    c.limits[0].quote = "  hotel   ACCOMMODATION is reimbursable up to INR 5,000 per night. "
    assert grounding_problems(c, clauses_of(TEP)) == []


# ---- LLM loop: ungrounded output is sent back and corrected ----
def test_model_is_retried_until_output_is_grounded(settings):
    bad = part(TEP).model_copy(deep=True)
    bad.limits[0].amount = 6000  # hallucinated
    answers = [bad, part(TEP)]
    calls = []

    def fn(messages, info: AgentInfo):
        calls.append(1)
        out = answers[min(len(calls) - 1, 1)]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, out.model_dump(mode="json"))])

    agent = build_interpreter_agent(FunctionModel(fn))
    _, result = run(interpret_document(TEP, DOCS[TEP], agent=agent, settings=settings))
    assert len(calls) == 2
    hotel = next(x for x in result.limits if x.category == "lodging")
    assert hotel.amount == 5000


def test_never_grounded_output_raises(settings):
    bad = part(TEP).model_copy(deep=True)
    bad.limits[0].amount = 6000
    agent = build_interpreter_agent(canned({TEP: bad}))
    with pytest.raises(PolicyInterpretationError):
        run(interpret_document(TEP, DOCS[TEP], agent=agent, settings=settings))


def test_document_name_is_stamped_by_code_not_the_model(settings):
    c = part(TEP).model_copy(deep=True)
    for lim in c.limits:
        lim.document = "made_up.md"
    agent = build_interpreter_agent(canned({TEP: c}))
    _, out = run(interpret_document(TEP, DOCS[TEP], agent=agent, settings=settings))
    assert {x.document for x in out.limits} == {TEP}


# ---- caching and adaptation to policy changes ----
def test_result_is_cached_by_document_hash_and_reinterpreted_on_change(settings):
    calls: list = []
    agent = build_interpreter_agent(canned({TEP: part(TEP)}, calls))
    run(interpret_document(TEP, DOCS[TEP], agent=agent, settings=settings))
    run(interpret_document(TEP, DOCS[TEP], agent=agent, settings=settings))
    assert len(calls) == 1  # second call served from cache

    edited = DOCS[TEP].replace("INR 5,000 per night", "INR 7,000 per night")
    edited_part = part(TEP, make_policy(hotel_cap=7000)).model_copy(deep=True)
    edited_part.limits[0].quote = "Hotel accommodation is reimbursable up to INR 7,000 per night."
    agent2 = build_interpreter_agent(canned({TEP: edited_part}, calls))
    _, out = run(interpret_document(TEP, edited, agent=agent2, settings=settings))
    assert len(calls) == 2  # changed document -> new interpretation
    assert next(x for x in out.limits if x.category == "lodging").amount == 7000


def test_load_policy_set_merges_documents_and_shares_category_ids(settings, tmp_path):
    calls: list = []
    agent = build_interpreter_agent(canned({TEP: part(TEP), GE: part(GE)}, calls))
    policy = run(load_policy_set(POLICY_DIR, agent=agent, settings=settings))

    assert set(policy.documents) == {TEP, GE}
    assert policy.limit_for("lodging", "M2").amount == 5000
    assert policy.limit_for("communication", "E1").amount == 800  # grade-specific limit from the other document
    assert "lodging" in policy.eligible_categories("M2")
    # the second document's prompt told the model which category ids already exist
    assert sum("already defined by other documents" in c for c in calls) == 1


# ---- retrieval ----
def test_clause_parsing_of_real_documents():
    tep = parse_clauses(TEP, DOCS[TEP])
    assert [c.ref for c in tep][:3] == ["TEP-1.1", "TEP-1.2", "TEP-1.3"]
    assert len(tep) == 13 and len(parse_clauses(GE, DOCS[GE])) == 6


def test_bm25_retrieves_the_relevant_clause():
    clauses = [c for d, t in DOCS.items() for c in parse_clauses(d, t)]
    idx = ClauseIndex(clauses)
    assert idx.search("hotel limit per night")[0][0].ref in ("TEP-2.1", "TEP-2.2")
    assert idx.search("client dinner attendees names")[0][0].ref == "TEP-5.1"
    assert idx.search("broadband monthly allowance")[0][0].ref.startswith("GE-3")
    assert idx.search("zzzz nothing") == []
```

### FILE: backend/tests/test_classifier.py  (102 lines)

```python
import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.classifier import UNKNOWN, build_classifier_agent, classify_receipt, describe_categories
from app.config import Settings
from app.models import ExtractedReceipt, FieldConfidence, LineItem, Receipt
from test_policy_evaluator import EMP, POLICY


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        llm_model="test:m",
        llm_call_delay_s=0,
        use_extraction_cache=False,
        cache_dir=tmp_path / "x",
        classification_cache_dir=tmp_path / "cls",
    )


def receipt(readable=True) -> ExtractedReceipt:
    r = Receipt(
        readable=readable,
        vendor="Lotus Grove Hotel",
        total=6000,
        currency="INR",
        category="hotel stay",
        nights=1,
        line_items=[LineItem(description="Room 1 night", amount=6000)],
        confidence=FieldConfidence(vendor=0.9, date=0.9, total=0.9),
    )
    return ExtractedReceipt(source_file="a.png", file_sha256="sha-a", model="m", receipt=r)


def answering(*answers: dict, seen: list | None = None):
    def fn(messages, info: AgentInfo):
        if seen is not None:
            seen.append(str(messages))
        n = len(seen) if seen is not None else 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answers[min(n, len(answers)) - 1])])

    return FunctionModel(fn)


GOOD = {"category": "lodging", "reasoning": "A hotel room for one night.", "confidence": 0.97}


def test_classifies_into_a_policy_category_and_caches(settings):
    seen: list = []
    agent = build_classifier_agent(answering(GOOD, seen=seen))
    c = run(classify_receipt(receipt(), EMP, POLICY, agent=agent, settings=settings))
    assert c.category == "lodging" and not c.needs_clarification
    run(classify_receipt(receipt(), EMP, POLICY, agent=agent, settings=settings))
    assert len(seen) == 1  # second call came from the cache


def test_prompt_lists_policy_categories_and_grade_eligibility(settings):
    seen: list = []
    exec_emp = EMP.model_copy(update={"grade": "E1"})
    run(
        classify_receipt(
            receipt(), exec_emp, POLICY, agent=build_classifier_agent(answering(GOOD, seen=seen)), settings=settings
        )
    )
    text = seen[0]
    assert "lodging" in text and "NOT available to grade E1" in text and "never reimbursable" in text
    assert "Room 1 night" in text


def test_unknown_category_is_sent_back_to_the_model(settings):
    seen: list = []
    agent = build_classifier_agent(answering({**GOOD, "category": "hotels"}, GOOD, seen=seen))
    c = run(classify_receipt(receipt(), EMP, POLICY, agent=agent, settings=settings))
    assert c.category == "lodging" and len(seen) == 2


def test_persistently_invalid_output_falls_back_to_unknown(settings):
    agent = build_classifier_agent(answering({**GOOD, "category": "hotels"}))
    c = run(classify_receipt(receipt(), EMP, POLICY, agent=agent, settings=settings))
    assert c.category == UNKNOWN and c.needs_clarification


def test_unreadable_receipt_skips_the_llm(settings):
    class Boom:
        async def run(self, *a, **k):
            raise AssertionError("must not call the LLM")

    c = run(classify_receipt(receipt(readable=False), EMP, POLICY, agent=Boom(), settings=settings))
    assert c.category == UNKNOWN


def test_category_description_marks_exclusions():
    text = describe_categories(POLICY, EMP)
    assert "personal_expenses" in text and "[never reimbursable]" in text
    assert "lodging" in text and "[available to grade M2]" in text
```

### FILE: backend/tests/test_claim.py  (180 lines)

```python
"""End-to-end claim logic over the synthetic receipts.

Ground truth stands in for a perfect extractor + classifier; the policy is the fixture that mirrors the
documents in data/policies. This checks the deterministic glue, not the LLMs.
"""

import datetime as dt
import json
from pathlib import Path

import pytest

from app.claim import ClaimInputs, ClaimState, ItemInput, ItemStatus, build_claim
from app.classifier import Classification
from app.models import ExtractedReceipt, FieldConfidence, Receipt
from app.policy.evaluator import Outcome
from test_policy_evaluator import EMP, POLICY, make_policy

TRUTH = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "ground_truth.json"
TODAY = dt.date(2026, 10, 9)


def load():
    extracted, cls = [], {}
    for t in json.loads(TRUTH.read_text()):
        r = Receipt(
            readable=True,
            vendor=t["vendor"],
            receipt_date=dt.date.fromisoformat(t["date"]) if t["date"] else None,
            total=t["total"],
            tax=t["tax"],
            currency=t["currency"],
            category=t["category"],
            confidence=FieldConfidence(vendor=0.95, date=0.95 if t["date"] else 0.0, total=0.95),
        )
        reasons = [] if t["date"] else ["Date missing"]
        extracted.append(
            ExtractedReceipt(
                source_file=t["file"],
                file_sha256=f"sha-{t['file']}",
                model="truth",
                receipt=r,
                needs_review=bool(reasons),
                review_reasons=reasons,
            )
        )
        cls[t["file"]] = Classification(category=t["category"], reasoning="from ground truth", confidence=0.95)
    return extracted, cls


@pytest.fixture(scope="module")
def data():
    return load()


def claim_of(data, inputs=None, policy=POLICY):
    extracted, cls = data
    return build_claim(extracted, cls, EMP, policy, inputs, today=TODAY)


def item(claim, prefix):
    return next(i for i in claim.items if i.file.startswith(prefix))


def test_first_pass_finds_every_planted_problem(data):
    claim = claim_of(data)
    assert claim.state is ClaimState.NEEDS_INPUT
    for dup in ("r21", "r22", "r23"):
        assert item(claim, dup).status is ItemStatus.DUPLICATE
    assert item(claim, "r22").duplicate_of.startswith("r04")
    assert item(claim, "r12").status is ItemStatus.INELIGIBLE  # months old
    assert item(claim, "r24").status is ItemStatus.INELIGIBLE  # personal expense, excluded by policy
    assert item(claim, "r10").status is ItemStatus.MISSING_INFO  # no date
    for flagged in ("r08", "r11", "r14"):  # meals over cap (x2) and training needing prior approval
        assert item(claim, flagged).status is ItemStatus.QUESTIONABLE
    assert item(claim, "r18").decision.outcome is Outcome.APPROVED  # client lunch within its limit


def test_ineligible_items_carry_the_clause_that_rejected_them(data):
    claim = claim_of(data)
    assert item(claim, "r24").decision.cites[0].ref == "TEP-1.3"
    assert item(claim, "r12").decision.cites[0].ref == "TEP-1.1"


def test_hotels_are_partially_reimbursed_up_to_the_policy_limit(data):
    claim = claim_of(data)
    for prefix in ("r03", "r19"):
        i = item(claim, prefix)
        assert i.decision.outcome is Outcome.PARTIAL
        assert i.eligible_inr == 5000
        assert i.total_inr > 5000
        assert "TEP-2.1" in i.decision.explanation


def test_questions_are_minimal(data):
    claim = claim_of(data)
    assert sorted(q.kind for q in claim.questions) == ["field", "justify", "justify", "justify", "purpose", "purpose"]
    assert len(claim.questions) < len(data[0]) / 3


def test_excluded_and_duplicates_do_not_count(data):
    claim = claim_of(data)
    assert claim.counts["duplicate"] == 3 and claim.counts["ineligible"] == 2
    included = [i for i in claim.items if i.status not in (ItemStatus.DUPLICATE, ItemStatus.INELIGIBLE)]
    assert claim.claimed_inr == pytest.approx(sum(i.total_inr for i in included if i.total_inr), abs=0.01)
    assert claim.eligible_inr < claim.claimed_inr


def test_foreign_currency_converted(data):
    assert item(claim_of(data), "r08").total_inr == pytest.approx(24.30 * 83.0, abs=0.01)


def test_answering_the_questions_makes_the_claim_ready(data):
    first = claim_of(data)
    inputs = ClaimInputs(
        group_purposes={q.target: "Customer visit and training trip" for q in first.questions if q.kind == "purpose"},
        items={
            "r10_missing_date.png": ItemInput(receipt_date=dt.date(2026, 9, 17)),
            "r08_foreign_usd.png": ItemInput(justification="Client dinner, manager approved"),
            "r11_overlimit_meal.png": ItemInput(justification="Client dinner, manager approved"),
            "r14_conf_fee.pdf": ItemInput(justification="Prior approval ref APR-1"),
        },
    )
    claim = claim_of(data, inputs)
    assert claim.questions == []
    assert claim.state is ClaimState.READY
    # the only gap between bills and reimbursement is the hotel excess above the limit
    assert claim.claimed_inr - claim.eligible_inr == pytest.approx((7168 - 5000) + (6496 - 5000), abs=0.01)


def test_changing_the_policy_changes_the_outcome_without_code_changes(data):
    claim = claim_of(data, policy=make_policy(hotel_cap=7000))
    assert item(claim, "r03").decision.outcome is Outcome.PARTIAL  # 7,168 still above 7,000
    assert item(claim, "r03").eligible_inr == 7000
    assert item(claim, "r19").decision.outcome is Outcome.APPROVED  # 6,496 now within the limit
    assert item(claim, "r19").eligible_inr == pytest.approx(6496, abs=0.01)


def test_ambiguous_category_asks_the_employee_and_their_choice_wins(data):
    extracted, cls = data
    cls = {
        **cls,
        "r01_cafe.png": Classification(
            category="meals",
            reasoning="could be client entertainment",
            confidence=0.4,
            needs_clarification=True,
            clarification_question="Was this a client meeting?",
        ),
    }
    first = build_claim(extracted, cls, EMP, POLICY, today=TODAY)
    q = next(q for q in first.questions if q.kind == "clarify")
    assert q.text.endswith("Was this a client meeting?") and "client_entertainment" in q.options
    assert item(first, "r01").status is ItemStatus.QUESTIONABLE

    inputs = ClaimInputs(items={"r01_cafe.png": ItemInput(category="client_entertainment")})
    second = build_claim(extracted, cls, EMP, POLICY, inputs, today=TODAY)
    assert not any(q.kind == "clarify" for q in second.questions)
    assert item(second, "r01").category_source == "employee"


def test_not_duplicate_override_keeps_the_receipt(data):
    claim = claim_of(data, ClaimInputs(items={"r21_dup_exact_cafe.png": ItemInput(not_duplicate=True)}))
    assert item(claim, "r21").status is not ItemStatus.DUPLICATE


def test_all_unusable_receipts_block_the_claim(data):
    extracted, cls = data
    old = [r for r in extracted if r.source_file.startswith("r12")]
    assert build_claim(old, cls, EMP, POLICY, today=TODAY).state is ClaimState.BLOCKED


def test_failed_extraction_asks_for_manual_entry():
    failed = ExtractedReceipt(
        source_file="x.png", file_sha256="x", model="m", review_reasons=["Automatic extraction failed"], error="boom"
    )
    claim = build_claim([failed], {}, EMP, POLICY, today=TODAY)
    q = claim.questions[0]
    assert q.kind == "field" and set(q.fields) == {"vendor", "date", "amount"}
    assert claim.state is ClaimState.NEEDS_INPUT
```

### FILE: backend/tests/test_finance.py  (45 lines)

```python
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
```

### FILE: backend/tests/test_state.py  (123 lines)

```python
import asyncio

import pytest
from pydantic_ai.exceptions import UserError

from factories import make_state, session_with
from test_policy_evaluator import make_policy


@pytest.fixture
def state(tmp_path):
    return make_state(tmp_path)


def item(session, prefix):
    return next(i for i in session.claim.items if i.file.startswith(prefix))


def test_every_answer_kind_updates_the_claim(state):
    s = session_with(state, "r05", "r13")
    f = "r05_stationery.png"
    state.apply_answer(s, "vendor", f, " Paper Co ")
    assert item(s, "r05").vendor == "Paper Co"
    state.apply_answer(s, "amount", f, "300")
    assert item(s, "r05").total == 300.0
    state.apply_answer(s, "currency", f, "usd")
    assert item(s, "r05").currency == "USD" and item(s, "r05").total_inr == 300 * 83
    state.apply_answer(s, "purpose_item", f, "Restock")
    assert s.inputs.items[f].business_purpose == "Restock"
    state.apply_answer(s, "category", "r13_parking.png", "fuel")
    assert item(s, "r13").category == "fuel" and item(s, "r13").category_source == "employee"
    state.apply_answer(s, "confirm", f, "")
    state.apply_answer(s, "not_duplicate", f, "")
    assert s.inputs.items[f].confirmed and s.inputs.items[f].not_duplicate


def test_group_purpose_removes_the_purpose_question(state):
    s = session_with(state, "r05", "r13")
    purposes = [q for q in s.claim.questions if q.kind == "purpose"]
    assert len(purposes) == 2  # the two bills are more than 3 days apart: two groups
    for q in purposes:
        state.apply_answer(s, "purpose_group", q.target, "Office restock")
    assert s.claim.questions == [] and s.claim.state.value == "ready"


@pytest.mark.parametrize(
    "kind,target,value",
    [
        ("bogus", "r05_stationery.png", ""),
        ("purpose_group", "g-1999-01-01", "x"),
        ("confirm", "ghost.png", ""),
        ("date", "r05_stationery.png", "not-a-date"),
        ("amount", "r05_stationery.png", "abc"),
        ("category", "r05_stationery.png", "yachts"),
    ],
)
def test_invalid_answers_raise_value_errors(state, kind, target, value):
    s = session_with(state, "r05")
    with pytest.raises(ValueError):
        state.apply_answer(s, kind, target, value)


def test_category_answers_need_a_loaded_policy(state):
    s = session_with(state, "r05")
    state._policy = None
    with pytest.raises(ValueError):
        state.apply_answer(s, "category", "r05_stationery.png", "meals")


def test_store_file_avoids_name_collisions(state):
    s = state.create_session()
    names = [state.store_file(s, "a.png", b"1"), state.store_file(s, "a.png", b"2"), state.store_file(s, "a.png", b"3")]
    assert names == ["a.png", "a_2.png", "a_3.png"]
    assert state.store_file(s, "../../evil.png", b"x") == "evil.png"  # path components are dropped


def test_processing_errors_are_reported_not_swallowed(state, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.state.process_files", boom)
    s = state.create_session()
    state.store_file(s, "x.png", b"data")
    asyncio.run(state.process(s, ["x.png"]))
    assert s.status == "error" and s.error.startswith("RuntimeError: boom")


def test_rebuild_is_a_noop_without_policy_or_receipts(state):
    state._policy = None
    s = state.create_session()
    state.rebuild(s)
    assert s.claim is None


def test_snapshot_tolerates_a_missing_classification(state):
    s = session_with(state, "r05")
    s.classifications.clear()
    snap = state.snapshot(s)
    assert snap["receipts"]["r05_stationery.png"]["classification"] is None
    assert snap["receipts"]["r05_stationery.png"]["thumb"].endswith("/thumb/r05_stationery.png")


def test_reloading_the_policy_recomputes_existing_claims(state, monkeypatch):
    s = session_with(state, "r03", "r19")
    assert s.claim.eligible_inr == 10000  # two hotel bills, each capped at 5,000

    async def load_changed_policy(*a, **k):
        return make_policy(hotel_cap=7000)

    monkeypatch.setattr("app.state.load_policy_set", load_changed_policy)
    asyncio.run(state.reload_policy())
    assert s.claim.eligible_inr == pytest.approx(7000 + 6496)


def test_a_missing_api_key_is_reported_in_plain_words(state, monkeypatch):
    async def no_key(*a, **k):
        raise UserError("Set the ANTHROPIC_API_KEY environment variable")

    monkeypatch.setattr("app.state.process_files", no_key)
    s = state.create_session()
    state.store_file(s, "x.png", b"data")
    asyncio.run(state.process(s, ["x.png"]))
    assert s.status == "error" and s.error.startswith("The AI model is not configured")
```

### FILE: backend/tests/test_chat_helpers.py  (102 lines)

```python
"""Chat agent tools and helpers, driven by a scripted fake model (no LLM)."""

import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app import chat
from app.chat import _resolve, build_chat_agent, describe_item, run_chat, summarise
from factories import make_state, session_with


@pytest.fixture
def state(tmp_path):
    return make_state(tmp_path)


def scripted(steps):
    """A fake model that calls the given (tool, args) steps in order, then answers 'ok'.
    `returns` always holds every tool result seen so far, in order."""
    remaining, returns = iter(steps), []

    def fn(messages, info):
        returns[:] = [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        step = next(remaining, None)
        part = TextPart("ok") if step is None else ToolCallPart(step[0], step[1])
        return ModelResponse(parts=[part])

    return FunctionModel(fn), returns


def chat_with(state, session, steps):
    model, returns = scripted(steps)
    state.chat_agent = build_chat_agent(model)
    assert asyncio.run(run_chat(state, session, "hello")) == "ok"
    return returns


def test_tools_before_any_receipts_give_helpful_answers(state):
    s = state.create_session()
    returns = chat_with(
        state, s, [("claim_status", {}), ("search_policy", {"query": "zzzz"}), ("explain_item", {"receipt": "nothing"})]
    )
    assert returns[0] == "No receipts have been processed yet."
    assert returns[1] == "No relevant policy clause found."
    assert "No receipt matches 'nothing'" in returns[2]


def test_search_policy_returns_clause_references(state):
    s = state.create_session()
    returns = chat_with(state, s, [("search_policy", {"query": "hotel limit per night"})])
    assert "TEP-2.1" in returns[0]


def test_record_answer_validation_messages_and_success(state):
    s = session_with(state, "r05", "r08")
    returns = chat_with(
        state,
        s,
        [
            ("record_answer", {"kind": "category", "target": "harbor", "value": "yachts"}),
            ("record_answer", {"kind": "confirm", "target": "ghost"}),
            ("record_answer", {"kind": "justification", "target": "harbor", "value": "Manager OK"}),
        ],
    )
    assert returns[0].startswith("Could not record that:") and "yachts" in returns[0]
    assert returns[1].startswith("No receipt matches")
    assert returns[2].startswith("Recorded.") and "Claim state" in returns[2]
    assert s.inputs.items["r08_foreign_usd.png"].justification == "Manager OK"


def test_explain_item_lists_clause_and_what_is_needed(state):
    s = session_with(state, "r08", "r05")
    returns = chat_with(state, s, [("explain_item", {"receipt": "r08"})])
    assert "Clause TEP-3.1" in returns[0] and "Needs: manager-approved justification" in returns[0]


def test_run_chat_builds_the_agent_lazily_and_keeps_history(state, monkeypatch):
    model, _ = scripted([])
    original = chat.build_chat_agent
    monkeypatch.setattr(chat, "build_chat_agent", lambda m: original(model))
    s = state.create_session()
    assert state.chat_agent is None
    asyncio.run(run_chat(state, s, "first"))
    first_len = len(s.chat_history)
    assert state.chat_agent is not None and first_len > 0
    asyncio.run(run_chat(state, s, "second"))
    assert len(s.chat_history) > first_len


def test_summary_and_receipt_resolution(state):
    s = session_with(state, "r05")
    assert "Claim state: needs_input" in summarise(s.claim) and "[purpose]" in summarise(s.claim)
    state.apply_answer(s, "purpose_group", s.claim.groups[0].id, "Restock")
    assert "No open questions." in summarise(s.claim)

    hotels = session_with(state, "r03", "r19")
    assert _resolve(hotels, "r03_hotel.pdf") == ("r03_hotel.pdf", "")
    file, err = _resolve(hotels, "lotus")
    assert file is None and "matches several receipts" in err
    assert describe_item(hotels.claim.items[0]).startswith("r03_hotel.pdf: Lotus Grove Hotel")
```

### FILE: backend/tests/test_edge_cases.py  (180 lines)

```python
"""Edge cases across evaluator, claim builder, duplicates, clause parser, extraction and pipeline."""

import asyncio
import datetime as dt

from PIL import Image
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.test import TestModel

from app.claim import ClaimInputs, ItemInput, ItemStatus, build_claim
from app.classifier import Classification
from app.config import Settings
from app.duplicates import DupKey, find_duplicates
from app.extraction import _user_content, build_agent, extract_receipt
from app.ingest import LoadedFile, Page, UnsupportedFileError
from app.models import ExtractedReceipt, FieldConfidence, Receipt
from app.pipeline import process_files
from app.policy.clauses import parse_clauses
from app.policy.evaluator import Outcome, UsageTracker
from test_claim import TODAY
from test_extraction import GOOD
from test_policy_evaluator import EMP, POLICY, ev


# ---------------------------------------------------------------- evaluator
def test_category_without_any_entitlement_is_rejected():
    p = POLICY.model_copy(deep=True)
    p.entitlements = [e for e in p.entitlements if e.category != "fuel"]
    d = ev("fuel", 100, policy=p)
    assert d.outcome is Outcome.REJECTED and "No policy clause makes" in d.explanation


def test_category_without_a_limit_is_approved_in_full():
    p = POLICY.model_copy(deep=True)
    p.limits = [lim for lim in p.limits if lim.category != "fuel"]
    d = ev("fuel", 99999, policy=p)
    assert d.outcome is Outcome.APPROVED and d.eligible_inr == 99999 and "no amount limit" in d.explanation


def test_partial_monthly_limit_is_consumed_across_receipts():
    p = POLICY.model_copy(deep=True)
    for lim in p.limits:
        if lim.category == "communication":
            lim.over_limit_action = "partial"
    t = UsageTracker()
    first = ev("communication", 1100, policy=p, tracker=t)
    second = ev("communication", 300, policy=p, tracker=t)
    third = ev("communication", 50, policy=p, tracker=t)
    assert first.outcome is Outcome.APPROVED
    assert second.outcome is Outcome.PARTIAL and second.eligible_inr == 100
    assert third.outcome is Outcome.REJECTED and "already used up" in third.explanation


# ---------------------------------------------------------------- claim builder
def _receipt(**over) -> Receipt:
    base = dict(
        readable=True,
        vendor="Paperwise",
        receipt_date=dt.date(2026, 9, 16),
        total=100.0,
        currency="INR",
        category="stationery",
        confidence=FieldConfidence(vendor=0.9, date=0.9, total=0.9),
    )
    base.update(over)
    return Receipt(**base)


def _extracted(receipt: Receipt, reasons=()) -> ExtractedReceipt:
    return ExtractedReceipt(
        source_file="a.png",
        file_sha256="sha-a",
        model="m",
        receipt=receipt,
        needs_review=bool(reasons),
        review_reasons=list(reasons),
    )


CLS = {"a.png": Classification(category="office_supplies", reasoning="stationery", confidence=0.9)}


def test_low_confidence_extraction_asks_for_confirmation_until_confirmed():
    e = _extracted(_receipt(), ["Low confidence on total (0.50)"])
    claim = build_claim([e], CLS, EMP, POLICY, today=TODAY)
    assert [q.kind for q in claim.questions].count("confirm") == 1
    assert claim.items[0].status is ItemStatus.QUESTIONABLE

    confirmed = ClaimInputs(items={"a.png": ItemInput(confirmed=True)})
    again = build_claim([e], CLS, EMP, POLICY, confirmed, today=TODAY)
    assert not any(q.kind == "confirm" for q in again.questions)


def test_unsupported_currency_asks_for_an_inr_amount():
    e = _extracted(_receipt(currency="XYZ"))
    claim = build_claim([e], CLS, EMP, POLICY, today=TODAY)
    q = next(q for q in claim.questions if q.kind == "field")
    assert "currency" in q.fields and claim.items[0].status is ItemStatus.MISSING_INFO

    fixed = build_claim([e], CLS, EMP, POLICY, ClaimInputs(items={"a.png": ItemInput(currency="INR")}), today=TODAY)
    assert not any(q.kind == "field" for q in fixed.questions)


# ---------------------------------------------------------------- duplicates and clauses
def test_different_vendors_with_same_date_and_amount_are_not_duplicates():
    d = dt.date(2026, 9, 14)
    keys = [DupKey("a", "s1", "Alpha Traders", d, 10.0, "INR"), DupKey("b", "s2", "Zeta Hotel", d, 10.0, "INR")]
    assert find_duplicates(keys) == {}


def test_wrapped_clause_lines_are_joined():
    text = "## 1. Rules\n\n1.1 First line\ncontinues here.\n\n1.2 Second clause.\n"
    clauses = parse_clauses("doc_name.md", text)
    assert clauses[0].text == "First line continues here." and clauses[0].ref == "DN-1.1"
    assert clauses[1].text == "Second clause." and clauses[1].heading == "Rules"


# ---------------------------------------------------------------- extraction
def test_pdf_text_is_added_to_the_prompt_but_the_file_name_never_is():
    plain = _user_content(LoadedFile("secret.pdf", "sha", [Page(b"x")]))
    assert plain[0] == "Extract the receipt in the attached image(s)."
    with_text = _user_content(LoadedFile("secret.pdf", "sha", [Page(b"x")], embedded_text="Total 5"))
    assert "Total 5" in with_text[0] and "secret" not in with_text[0]


def _png(tmp_path):
    p = tmp_path / "r.png"
    Image.new("RGB", (60, 80), "white").save(p)
    return p


def test_call_delay_is_applied_and_a_cache_miss_falls_through_to_the_llm(tmp_path, monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("app.extraction.asyncio.sleep", fake_sleep)
    settings = Settings(llm_model="test:m", llm_call_delay_s=0.5, use_extraction_cache=True, cache_dir=tmp_path / "c")
    result = asyncio.run(
        extract_receipt(_png(tmp_path), agent=build_agent(TestModel(custom_output_args=GOOD)), settings=settings)
    )
    assert result.error is None and slept == [0.5]


# ---------------------------------------------------------------- pipeline
def test_failures_become_failed_items_and_progress_is_reported(tmp_path, monkeypatch):
    notes = tmp_path / "notes.txt"
    notes.write_text("not a receipt")
    flaky = _png(tmp_path)
    ok = tmp_path / "ok.png"
    Image.new("RGB", (60, 80), "white").save(ok)

    async def fake_extract(path, *, agent, settings):
        if path.name == "notes.txt":
            raise UnsupportedFileError("notes.txt: unsupported type '.txt'")
        if path.name == "r.png":
            raise ModelHTTPError(500, "m", body=None)
        return _extracted(_receipt()).model_copy(update={"source_file": path.name})

    async def fake_classify(e, employee, policy, *, agent, settings):
        return Classification(category="office_supplies", reasoning="ok", confidence=0.9)

    monkeypatch.setattr("app.pipeline.extract_receipt", fake_extract)
    monkeypatch.setattr("app.pipeline.classify_receipt", fake_classify)
    ticks = []
    settings = Settings(
        llm_model="anthropic:claude-sonnet-5-5",
        llm_call_delay_s=0,
        use_extraction_cache=False,
        cache_dir=tmp_path / "c",
    )
    extracted, cls = asyncio.run(
        process_files([notes, flaky, ok], EMP, POLICY, settings=settings, on_progress=lambda: ticks.append(1))
    )
    by_name = {e.source_file: e for e in extracted}
    assert len(ticks) == 3
    assert by_name["notes.txt"].error and by_name["r.png"].error and by_name["ok.png"].error is None
    assert by_name["notes.txt"].receipt is None and by_name["notes.txt"].needs_review
    assert cls["notes.txt"].category == "unknown" and cls["ok.png"].category == "office_supplies"
```

### FILE: backend/tests/test_api_upload_and_errors.py  (179 lines)

```python
"""API tests for the upload path and every error branch. The extraction/classification pipeline is replaced by a
fake that returns ground truth, so no LLM, cache or network is involved."""

import datetime as dt
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError, UserError

from app.main import MAX_BYTES, MAX_FILES, _env_today, create_app
from app.policy.interpreter import PolicyInterpretationError
from factories import make_state, truth_for

RECEIPTS = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "receipts"


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    extracted, classifications = truth_for("r05", "r13", "r08")

    async def fake_process_files(paths, employee, policy, *, settings=None, concurrency=4, on_progress=None):
        out, classes = [], {}
        for p in paths:
            src = next(e for e in extracted if p.name.startswith(Path(e.source_file).stem))
            out.append(src.model_copy(update={"source_file": p.name}))
            classes[p.name] = classifications[src.source_file]
            if on_progress:
                on_progress()
        return out, classes

    monkeypatch.setattr("app.state.process_files", fake_process_files)
    with TestClient(create_app(state)) as c:
        c.state = state
        yield c


def upload(client, sid, *names):
    files = [("files", (n, (RECEIPTS / n).read_bytes(), "image/png")) for n in names]
    return client.post(f"/api/sessions/{sid}/receipts", files=files)


def wait_ready(client, sid, timeout=10):
    t = time.time()
    while time.time() - t < timeout:
        snap = client.get(f"/api/sessions/{sid}").json()
        if snap["status"] in ("ready", "error"):
            return snap
        time.sleep(0.05)
    raise AssertionError("processing timed out")


def new_session(client):
    return client.post("/api/sessions").json()["id"]


def test_upload_processes_files_and_builds_a_claim(client):
    sid = new_session(client)
    r = upload(client, sid, "r05_stationery.png", "r13_parking.png")
    assert r.status_code == 202 and r.json()["status"] == "processing"
    snap = wait_ready(client, sid)
    assert snap["status"] == "ready"
    assert [i["file"] for i in snap["claim"]["items"]] == ["r05_stationery.png", "r13_parking.png"]
    assert snap["progress"] == {"done": 2, "total": 2}
    assert client.get(snap["receipts"]["r05_stationery.png"]["thumb"]).status_code == 200


def test_uploading_the_same_name_twice_keeps_both_files(client):
    sid = new_session(client)
    upload(client, sid, "r05_stationery.png")
    wait_ready(client, sid)
    upload(client, sid, "r05_stationery.png")
    snap = wait_ready(client, sid)
    assert set(snap["receipts"]) == {"r05_stationery.png", "r05_stationery_2.png"}


def test_too_many_files_are_rejected(client):
    sid = new_session(client)
    files = [("files", (f"a{i}.png", b"x", "image/png")) for i in range(MAX_FILES + 1)]
    r = client.post(f"/api/sessions/{sid}/receipts", files=files)
    assert r.status_code == 400 and "At most" in r.json()["detail"]


def test_oversized_file_is_rejected(client):
    sid = new_session(client)
    r = client.post(
        f"/api/sessions/{sid}/receipts", files=[("files", ("big.png", b"x" * (MAX_BYTES + 1), "image/png"))]
    )
    assert r.status_code == 413


def test_upload_and_demo_are_refused_while_processing(client):
    sid = new_session(client)
    client.state.get(sid).status = "processing"
    assert upload(client, sid, "r05_stationery.png").status_code == 409
    assert client.post(f"/api/sessions/{sid}/demo").status_code == 409


def test_upload_is_refused_after_submission(client):
    sid = new_session(client)
    client.state.get(sid).submitted_ref = "RMB-1"
    assert upload(client, sid, "r05_stationery.png").status_code == 409


def test_thumbnail_of_an_unreadable_file_is_415(client):
    sid = new_session(client)
    client.state.store_file(client.state.get(sid), "bad.png", b"not an image")
    assert client.get(f"/api/sessions/{sid}/thumb/bad.png").status_code == 415
    assert client.get(f"/api/sessions/{sid}/thumb/never-uploaded.png").status_code == 404


def test_submitting_an_empty_session_is_409(client):
    sid = new_session(client)
    r = client.post(f"/api/sessions/{sid}/submit")
    assert r.status_code == 409 and r.json()["detail"] == "Nothing to submit"


def test_chat_ai_failures_map_to_http_errors(client, monkeypatch):
    sid = new_session(client)
    upload(client, sid, "r05_stationery.png")
    wait_ready(client, sid)

    async def no_key(*a, **k):
        raise UserError("no API key")

    async def overloaded(*a, **k):
        raise ModelHTTPError(500, "m", body=None)

    monkeypatch.setattr("app.main.run_chat", no_key)
    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"})
    assert r.status_code == 503 and "not configured" in r.json()["detail"]
    monkeypatch.setattr("app.main.run_chat", overloaded)
    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"})
    assert r.status_code == 502 and "ModelHTTPError" in r.json()["detail"]


def test_policy_view_failures_are_reported(client, monkeypatch):
    async def broken():
        raise PolicyInterpretationError("could not interpret")

    monkeypatch.setattr(client.state, "policy", broken)
    r = client.get("/api/policy")
    assert r.status_code == 502 and "PolicyInterpretationError" in r.json()["detail"]


def test_failed_policy_edit_restores_the_previous_text(client, monkeypatch):
    path = client.state.policy_dir / "travel_expense_policy.md"
    original = path.read_text()

    async def no_key():
        raise UserError("no API key")

    monkeypatch.setattr(client.state, "reload_policy", no_key)
    r = client.put("/api/policy/travel_expense_policy.md", json={"text": original.replace("5,000", "9,000")})
    assert r.status_code == 503
    assert path.read_text() == original


def test_failed_policy_reset_is_reported(client, monkeypatch):
    async def overloaded():
        raise ModelHTTPError(503, "m", body=None)

    monkeypatch.setattr(client.state, "reload_policy", overloaded)
    assert client.post("/api/policy/reset").status_code == 502


def test_unknown_finance_claim_is_404_and_health_reports_the_model(client):
    assert client.get("/api/finance/claims/RMB-0").status_code == 404
    health = client.get("/api/health").json()
    assert health["ok"] is True and health["model"]


def test_claim_today_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLAIM_TODAY", "2026-10-12")
    assert _env_today() == dt.date(2026, 10, 12)
    monkeypatch.delenv("CLAIM_TODAY")
    assert _env_today() is None
```

### FILE: backend/tests/test_api.py  (201 lines)

```python
"""API tests. They run offline: AI results come from the committed caches (the demo fallback path),
and the chat agent is a scripted fake model."""

import datetime as dt
import time

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.chat import build_chat_agent
from app.config import get_settings
from app.extraction import _slug
from app.main import create_app
from app.state import AppState

TODAY = dt.date(2026, 10, 12)


def caches_are_warm(settings) -> bool:
    """True when extraction, policy and classification results exist for the configured model."""
    slug = _slug(settings.llm_model)
    dirs = (settings.cache_dir, settings.policy_cache_dir, settings.classification_cache_dir)
    return all(any((d / slug).glob("*.json")) for d in dirs)


@pytest.fixture
def client(tmp_path):
    # Uses LLM_MODEL from the environment/.env. These tests replay AI results from data/cache, so they are skipped
    # (not failed) on a cold checkout; warm the caches once with the same model:
    #   python tools/run_pipeline.py --today 2026-10-12
    settings = get_settings()
    if not caches_are_warm(settings):
        pytest.skip("AI caches are cold for this LLM_MODEL; run `python tools/run_pipeline.py --today 2026-10-12` once")
    state = AppState(settings, runtime_dir=tmp_path, today=TODAY)
    with TestClient(create_app(state)) as c:
        c.state = state
        yield c


def wait_ready(client, sid, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        snap = client.get(f"/api/sessions/{sid}").json()
        if snap["status"] in ("ready", "error"):
            return snap
        time.sleep(0.2)
    raise AssertionError("processing timed out")


def demo_session(client):
    sid = client.post("/api/sessions").json()["id"]
    assert client.post(f"/api/sessions/{sid}/demo").status_code == 202
    snap = wait_ready(client, sid)
    assert snap["status"] == "ready", snap["error"]
    return sid, snap


def answer_everything(client, sid, snap):
    for q in snap["claim"]["questions"]:
        kind = {
            "purpose": "purpose_group",
            "justify": "justification",
            "field": "date",
            "clarify": "confirm",
            "confirm": "confirm",
        }[q["kind"]]
        value = {"purpose_group": "Customer visit", "justification": "Manager approved", "date": "2026-09-17"}.get(
            kind, ""
        )
        r = client.post(f"/api/sessions/{sid}/answers", json={"kind": kind, "target": q["target"], "value": value})
        assert r.status_code == 200, r.text
        snap = r.json()
    return snap


def test_demo_receipts_become_a_claim_with_decisions(client):
    sid, snap = demo_session(client)
    claim = snap["claim"]
    assert claim["state"] == "needs_input"
    assert claim["counts"]["duplicate"] == 3
    assert claim["eligible_inr"] < claim["claimed_inr"]
    hotel = next(i for i in claim["items"] if i["file"].startswith("r03"))
    assert hotel["decision"]["outcome"] == "partial" and hotel["decision"]["cites"][-1]["ref"] == "TEP-2.1"
    assert snap["receipts"]["r03_hotel.pdf"]["thumb"].endswith("/thumb/r03_hotel.pdf")


def test_thumbnails_are_served_for_images_and_pdfs(client):
    sid, _ = demo_session(client)
    for name in ("r01_cafe.png", "r03_hotel.pdf"):
        r = client.get(f"/api/sessions/{sid}/thumb/{name}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/sessions/{sid}/thumb/../../etc/passwd").status_code == 404


def test_answering_then_submitting_reaches_the_mock_finance_system(client):
    sid, snap = demo_session(client)
    early = client.post(f"/api/sessions/{sid}/submit")
    assert early.status_code == 409  # not ready yet

    snap = answer_everything(client, sid, snap)
    assert snap["claim"]["state"] == "ready", snap["claim"]["questions"]
    r = client.post(f"/api/sessions/{sid}/submit")
    assert r.status_code == 200
    ref = r.json()["submission"]["id"]
    assert ref.startswith("RMB-")

    rows = client.get("/api/finance/claims").json()
    assert [x["id"] for x in rows] == [ref]
    stored = client.get(f"/api/finance/claims/{ref}").json()
    assert stored["payload"]["state"] == "ready" and stored["eligible_inr"] == snap["claim"]["eligible_inr"]
    assert client.post(f"/api/sessions/{sid}/submit").status_code == 409  # no double submit
    assert (
        client.post(f"/api/sessions/{sid}/answers", json={"kind": "confirm", "target": "r01_cafe.png"}).status_code
        == 409
    )


def test_bad_inputs_are_rejected(client):
    sid = client.post("/api/sessions").json()["id"]
    assert (
        client.post(f"/api/sessions/{sid}/receipts", files=[("files", ("notes.txt", b"hi", "text/plain"))]).status_code
        == 400
    )
    assert client.post("/api/sessions/nope/demo").status_code == 404
    sid, snap = demo_session(client)
    for body in (
        {"kind": "bogus", "target": "r01_cafe.png"},
        {"kind": "category", "target": "r01_cafe.png", "value": "yachts"},
        {"kind": "date", "target": "r01_cafe.png", "value": "not-a-date"},
        {"kind": "confirm", "target": "ghost.png"},
    ):
        assert client.post(f"/api/sessions/{sid}/answers", json=body).status_code == 422


def test_editing_the_policy_document_changes_the_claim_without_code(client):
    sid, before = demo_session(client)
    doc = next(d for d in client.get("/api/policy").json()["documents"] if d["name"] == "travel_expense_policy.md")
    assert "INR 5,000 per night" in doc["text"]

    new = client.put(
        "/api/policy/travel_expense_policy.md",
        json={"text": doc["text"].replace("INR 5,000 per night", "INR 7,000 per night")},
    )
    assert new.status_code == 200, new.text
    lodging = next(x for x in new.json()["interpreted"]["limits"] if x["category"] == "lodging")
    assert lodging["amount"] == 7000

    after = client.get(f"/api/sessions/{sid}").json()["claim"]
    assert after["eligible_inr"] > before["claim"]["eligible_inr"]
    assert next(i for i in after["items"] if i["file"].startswith("r19"))["decision"]["outcome"] == "approved"

    assert client.post("/api/policy/reset").status_code == 200
    reset = client.get(f"/api/sessions/{sid}").json()["claim"]
    assert reset["eligible_inr"] == before["claim"]["eligible_inr"]


def test_unknown_policy_document_is_404(client):
    assert client.put("/api/policy/missing.md", json={"text": "x" * 20}).status_code == 404


def scripted_chat(client, steps):
    """steps: list of (tool name, args) the fake model will call in order, then it replies 'Done'."""
    calls, returns = iter(steps), []

    def fn(messages, info: AgentInfo):
        returns[:] = [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        nxt = next(calls, None)
        if nxt is None:
            return ModelResponse(parts=[TextPart("Done")])
        return ModelResponse(parts=[ToolCallPart(nxt[0], nxt[1])])

    client.state.chat_agent = build_chat_agent(FunctionModel(fn))
    return returns


def test_chat_agent_explains_with_clauses_and_records_answers(client):
    sid, snap = demo_session(client)
    group = snap["claim"]["groups"][-1]["id"]
    returns = scripted_chat(
        client,
        [
            ("explain_item", {"receipt": "lotus"}),  # two hotels -> ambiguous
            ("explain_item", {"receipt": "r03"}),
            ("search_policy", {"query": "hotel limit per night"}),
            ("record_answer", {"kind": "purpose_group", "target": group, "value": "Customer visit"}),
        ],
    )
    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "why was my hotel cut?"})
    assert r.status_code == 200 and r.json()["reply"] == "Done"
    assert "matches several receipts" in returns[0]
    assert "TEP-2.1" in returns[1] and "INR 5,000" in returns[1]
    assert "TEP-2.1" in returns[2]  # retrieval found the hotel clause
    assert client.state.sessions[sid].inputs.group_purposes[group] == "Customer visit"
    assert not any(q["kind"] == "purpose" and q["target"] == group for q in r.json()["session"]["claim"]["questions"])


def test_chat_needs_receipts_first(client):
    sid = client.post("/api/sessions").json()["id"]
    assert client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"}).status_code == 409
```

