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
