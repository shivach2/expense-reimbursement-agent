"""Turn extracted + classified receipts into a claim: what is complete, missing or questionable.

AI decides what each expense is (classifier) and what the policy allows (interpreter);
this module is the deterministic glue: dedupe, enforce the interpreted constraints with
exact arithmetic, group, and work out the minimal questions needed to reach READY.
Every item carries the policy clauses and plain-language reasons behind its status.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from app.classifier import UNKNOWN, Classification, unknown_classification
from app.currency import to_inr
from app.duplicates import DupKey, find_duplicates
from app.grouping import Group, group_by_date
from app.models import ExtractedReceipt
from app.policy.evaluator import Decision, Outcome, UsageTracker, evaluate_line
from app.policy.schema import Employee, PolicySet

_SOFT_REASON_PREFIXES = ("Low confidence", "Line items")
CLARIFY_BELOW_CONFIDENCE = 0.75


class ItemStatus(StrEnum):
    COMPLETE = "complete"
    MISSING_INFO = "missing_info"
    QUESTIONABLE = "questionable"
    DUPLICATE = "duplicate"
    INELIGIBLE = "ineligible"


class ClaimState(StrEnum):
    READY = "ready"
    NEEDS_INPUT = "needs_input"
    BLOCKED = "blocked"


class ItemInput(BaseModel):
    """What the employee told us about one receipt (answers and corrections)."""

    vendor: str | None = None
    receipt_date: dt.date | None = None
    total: float | None = None
    currency: str | None = None
    category: str | None = None  # employee overrides the AI's category
    business_purpose: str | None = None
    justification: str | None = None
    confirmed: bool = False  # "the extracted details are right"
    not_duplicate: bool = False

    def has_corrections(self) -> bool:
        return any(v is not None for v in (self.vendor, self.receipt_date, self.total, self.currency))


class ClaimInputs(BaseModel):
    items: dict[str, ItemInput] = Field(default_factory=dict)  # keyed by source file
    group_purposes: dict[str, str] = Field(default_factory=dict)  # keyed by group id


class ClaimItem(BaseModel):
    file: str
    vendor: str | None
    receipt_date: dt.date | None
    total: float | None
    currency: str
    total_inr: float | None
    category: str
    category_source: str = "ai"  # ai | employee
    category_reasoning: str = ""
    status: ItemStatus
    reasons: list[str] = Field(default_factory=list)
    decision: Decision | None = None
    eligible_inr: float = 0.0
    duplicate_of: str | None = None
    group_id: str | None = None


class ClaimGroup(BaseModel):
    id: str
    title: str
    start: dt.date
    end: dt.date
    files: list[str]
    eligible_inr: float


class Question(BaseModel):
    id: str
    kind: str  # field | clarify | purpose | justify | confirm
    target: str  # file name or group id
    text: str
    fields: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    state: ClaimState
    employee: Employee
    items: list[ClaimItem]
    groups: list[ClaimGroup]
    questions: list[Question]
    eligible_by_category: dict[str, float]
    claimed_inr: float  # what the bills add up to (included items)
    eligible_inr: float  # what policy allows to be reimbursed
    counts: dict[str, int]


@dataclass
class _Eff:
    """An extracted receipt with the employee's corrections applied."""

    e: ExtractedReceipt
    inp: ItemInput
    vendor: str | None
    date: dt.date | None
    total: float | None
    currency: str
    total_inr: float | None

    @property
    def file(self) -> str:
        return self.e.source_file

    @property
    def label(self) -> str:
        return self.vendor or self.file


def _effective(e: ExtractedReceipt, inp: ItemInput) -> _Eff:
    r = e.receipt
    total = inp.total if inp.total is not None else (r.total if r else None)
    currency = (inp.currency or (r.currency if r else "INR")).upper()
    return _Eff(
        e,
        inp,
        inp.vendor or (r.vendor if r else None),
        inp.receipt_date or (r.receipt_date if r else None),
        total,
        currency,
        to_inr(total, currency) if total is not None else None,
    )


def _dup_key(x: _Eff) -> DupKey:
    receipt_number = x.e.receipt.receipt_number if x.e.receipt else None
    return DupKey(x.file, x.e.file_sha256, x.vendor, x.date, x.total, x.currency, receipt_number)


def _new_item(x: _Eff, cls: Classification, **extra) -> ClaimItem:
    """A claim item for one receipt; the employee's category choice wins over the AI's."""
    chosen = bool(x.inp.category)
    return ClaimItem(
        file=x.file,
        vendor=x.vendor,
        receipt_date=x.date,
        total=x.total,
        currency=x.currency,
        total_inr=x.total_inr,
        category=x.inp.category or cls.category,
        category_source="employee" if chosen else "ai",
        category_reasoning="Chosen by the employee." if chosen else cls.reasoning,
        **extra,
    )


def _triage(
    effs: list[_Eff],
    classifications: Mapping[str, Classification],
    employee: Employee,
    policy: PolicySet,
    today: dt.date,
) -> tuple[dict[str, ClaimItem], dict[str, Classification], list[_Eff]]:
    """Stage 1: mark duplicates, evaluate the policy for the rest, and set aside what policy rejects.

    Returns every item by file name, the classification used for each file, and the receipts that stay in play.
    """
    dups = find_duplicates([_dup_key(x) for x in effs], exempt={x.file for x in effs if x.inp.not_duplicate})
    items: dict[str, ClaimItem] = {}
    cls_of: dict[str, Classification] = {}
    active: list[_Eff] = []
    tracker = UsageTracker()  # shared so per-day and per-month limits span receipts, in input order
    for x in effs:
        cls = classifications.get(x.file) or unknown_classification("Not classified.")
        cls_of[x.file] = cls
        if x.file in dups:
            d = dups[x.file]
            reason = f"Duplicate of {d.original} ({d.reason}); left out of the claim"
            items[x.file] = _new_item(x, cls, status=ItemStatus.DUPLICATE, duplicate_of=d.original, reasons=[reason])
            continue
        decision = evaluate_line(
            category=x.inp.category or cls.category,
            claimed_inr=x.total_inr or 0.0,
            date=x.date,
            employee=employee,
            policy=policy,
            today=today,
            tracker=tracker,
            nights=x.e.receipt.nights if x.e.receipt else None,
            justification=x.inp.justification,
        )
        if decision.outcome is Outcome.REJECTED:
            items[x.file] = _new_item(
                x, cls, status=ItemStatus.INELIGIBLE, decision=decision, reasons=[decision.explanation]
            )
            continue
        items[x.file] = _new_item(x, cls, status=ItemStatus.COMPLETE, decision=decision)
        active.append(x)
    return items, cls_of, active


def _missing_basics(x: _Eff) -> list[str]:
    missing = [name for name, value in (("vendor", x.vendor), ("date", x.date), ("amount", x.total)) if value is None]
    if x.total is not None and x.total_inr is None:
        missing.append("currency")  # unsupported currency: ask for an INR amount
    return missing


def _category_unclear(x: _Eff, cls: Classification, item: ClaimItem, policy: PolicySet) -> bool:
    """Only interrupt the employee when the model both asks and is genuinely unsure (or the category is unusable)."""
    if x.inp.category:
        return False
    unsure = cls.needs_clarification and cls.confidence < CLARIFY_BELOW_CONFIDENCE
    return unsure or item.category == UNKNOWN or item.category not in policy.category_ids()


def _assess_item(
    x: _Eff, item: ClaimItem, cls: Classification, policy: PolicySet, eligible_cats: list[str], inputs: ClaimInputs
) -> tuple[list[Question], bool]:
    """Stage 2: decide one item's status and the questions it needs.

    Returns (questions, needs_business_purpose). Basics are asked first; nothing else is asked for that receipt.
    """
    decision = item.decision
    assert decision is not None
    questions: list[Question] = []

    missing = _missing_basics(x)
    if missing:
        item.status = ItemStatus.MISSING_INFO
        item.reasons.append(f"Missing {', '.join(missing)}")
        text = f"{x.label}: please provide the {' and '.join(missing)}."
        questions.append(Question(id=f"field:{x.file}", kind="field", target=x.file, fields=missing, text=text))
        return questions, False

    status = ItemStatus.COMPLETE
    if _category_unclear(x, cls, item, policy):
        status = ItemStatus.QUESTIONABLE
        ask = cls.clarification_question or "Which category does this expense belong to?"
        item.reasons.append("Category unclear")
        questions.append(
            Question(
                id=f"clarify:{x.file}", kind="clarify", target=x.file, options=eligible_cats, text=f"{x.label}: {ask}"
            )
        )
    elif decision.outcome is Outcome.FLAGGED:
        status = ItemStatus.QUESTIONABLE
        item.reasons.append(decision.explanation)
        needed = " and ".join(decision.needs) or "a justification"
        text = f"{x.label}: {decision.explanation} Please provide {needed}."
        questions.append(Question(id=f"justify:{x.file}", kind="justify", target=x.file, text=text))
    elif decision.outcome is Outcome.PARTIAL:
        item.reasons.append(decision.explanation)

    soft = [r for r in x.e.review_reasons if r.startswith(_SOFT_REASON_PREFIXES)]
    if soft and not (x.inp.confirmed or x.inp.has_corrections()):
        status = ItemStatus.QUESTIONABLE
        item.reasons.extend(soft)
        text = f"{x.label}: {'; '.join(soft)}. Are the extracted details correct?"
        questions.append(Question(id=f"confirm:{x.file}", kind="confirm", target=x.file, text=text))

    needs_purpose = not (x.inp.business_purpose or inputs.group_purposes.get(item.group_id or ""))
    if needs_purpose:
        if status is ItemStatus.COMPLETE:
            status = ItemStatus.MISSING_INFO
        item.reasons.append("Business purpose needed")
    item.status = status
    item.eligible_inr = decision.eligible_inr if decision.outcome is not Outcome.FLAGGED else 0.0
    return questions, needs_purpose


def _purpose_questions(missing: dict[str, list[str]], groups: dict[str, Group]) -> list[Question]:
    """One business-purpose question per trip group, not per receipt."""
    return [
        Question(
            id=f"purpose:{gid}",
            kind="purpose",
            target=gid,
            text=f"What was the business purpose of these {len(files)} receipt(s)? ({groups[gid].title})",
        )
        for gid, files in missing.items()
    ]


def _assemble(
    effs: list[_Eff], items: dict[str, ClaimItem], groups: list[Group], questions: list[Question], employee: Employee
) -> Claim:
    """Stage 3: claim state and totals over the items that are still included."""
    included = [i for i in items.values() if i.status not in (ItemStatus.DUPLICATE, ItemStatus.INELIGIBLE)]
    if not included:
        state = ClaimState.BLOCKED
    elif all(i.status is ItemStatus.COMPLETE for i in included):
        state = ClaimState.READY
    else:
        state = ClaimState.NEEDS_INPUT

    by_cat: dict[str, float] = defaultdict(float)
    for i in included:
        by_cat[i.category] += i.eligible_inr
    counts: dict[str, int] = defaultdict(int)
    for i in items.values():
        counts[i.status.value] += 1

    return Claim(
        state=state,
        employee=employee,
        items=[items[x.file] for x in effs],
        groups=[
            ClaimGroup(
                id=g.id,
                title=g.title,
                start=g.start,
                end=g.end,
                files=g.files,
                eligible_inr=round(sum(items[f].eligible_inr for f in g.files), 2),
            )
            for g in groups
        ],
        questions=questions,
        eligible_by_category={k: round(v, 2) for k, v in by_cat.items()},
        claimed_inr=round(sum(i.total_inr or 0 for i in included), 2),
        eligible_inr=round(sum(by_cat.values()), 2),
        counts=dict(counts),
    )


def build_claim(
    extracted: Sequence[ExtractedReceipt],
    classifications: Mapping[str, Classification],
    employee: Employee,
    policy: PolicySet,
    inputs: ClaimInputs | None = None,
    *,
    today: dt.date | None = None,
) -> Claim:
    """Turn extracted and classified receipts into a claim: statuses, minimal questions, totals and state."""
    inputs = inputs or ClaimInputs()
    today = today or dt.date.today()
    effs = [_effective(e, inputs.items.get(e.source_file, ItemInput())) for e in extracted]

    items, cls_of, active = _triage(effs, classifications, employee, policy, today)

    groups = group_by_date([(x.file, x.date) for x in active if x.date is not None])
    group_of = {f: g.id for g in groups for f in g.files}
    eligible_cats = policy.eligible_categories(employee.grade)

    questions: list[Question] = []
    purpose_missing: dict[str, list[str]] = defaultdict(list)
    for x in active:
        item = items[x.file]
        item.group_id = group_of.get(x.file)
        item_questions, needs_purpose = _assess_item(x, item, cls_of[x.file], policy, eligible_cats, inputs)
        questions.extend(item_questions)
        if needs_purpose and item.group_id:
            purpose_missing[item.group_id].append(x.file)
    questions.extend(_purpose_questions(purpose_missing, {g.id: g for g in groups}))

    return _assemble(effs, items, groups, questions, employee)
