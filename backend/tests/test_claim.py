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
