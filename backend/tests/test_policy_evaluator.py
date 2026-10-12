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
