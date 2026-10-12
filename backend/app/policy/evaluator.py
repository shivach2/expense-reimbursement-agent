"""Deterministic enforcement of interpreted policy constraints.

All money arithmetic happens here, never in the LLM. Every decision carries the
clause references and verbatim quotes it relied on, plus a plain-language
explanation built from the computed numbers.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field

from app.currency import to_inr
from app.policy.clauses import doc_code
from app.policy.schema import Employee, Limit, PolicySet, _Cited


class Outcome(StrEnum):
    APPROVED = "approved"
    PARTIAL = "partial"
    FLAGGED = "flagged"  # resolvable: needs a justification, approval or clarification
    REJECTED = "rejected"


class ClauseCite(BaseModel):
    ref: str
    document: str
    quote: str


class Decision(BaseModel):
    outcome: Outcome
    category: str
    claimed_inr: float
    eligible_inr: float
    explanation: str
    cites: list[ClauseCite] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)


class UsageTracker:
    """Tracks how much of per-day / per-month limits earlier receipts have used."""

    def __init__(self) -> None:
        self.used: dict[tuple, float] = defaultdict(float)


def inr(x: float) -> str:
    return f"INR {x:,.0f}" if abs(x - round(x)) < 0.005 else f"INR {x:,.2f}"


def _cite(item: _Cited) -> ClauseCite:
    return ClauseCite(ref=f"{doc_code(item.document)}-{item.clause}", document=item.document, quote=item.quote)


def _quoted(c: ClauseCite) -> str:
    return f'Policy {c.ref}: "{c.quote}"'


def _bucket(limit: Limit, date: dt.date | None) -> tuple:
    if limit.unit == "per_day" and date:
        return (limit.document, limit.clause, date)
    if limit.unit == "per_month" and date:
        return (limit.document, limit.clause, date.year, date.month)
    return ()  # per receipt / per night: nothing shared across receipts


def evaluate_line(
    *,
    category: str,
    claimed_inr: float,
    date: dt.date | None,
    employee: Employee,
    policy: PolicySet,
    today: dt.date,
    tracker: UsageTracker,
    nights: int | None = None,
    justification: str | None = None,
) -> Decision:
    def decide(
        outcome: Outcome, eligible: float, text: str, cites: list[ClauseCite], needs: list[str] | None = None
    ) -> Decision:
        return Decision(
            outcome=outcome,
            category=category,
            claimed_inr=claimed_inr,
            eligible_inr=round(eligible, 2),
            explanation=text,
            cites=cites,
            needs=needs or [],
        )

    label = policy.label(category)

    if category not in policy.category_ids():
        return decide(
            Outcome.FLAGGED, 0.0, "No policy category matches this expense; please choose one.", [], ["category"]
        )

    if (x := policy.exclusion_for(category)) is not None:
        c = _cite(x)
        return decide(Outcome.REJECTED, 0.0, f"{label} is not reimbursable: {x.reason}. {_quoted(c)}", [c])

    if not any(policy.entitlements_for(category)):
        return decide(Outcome.REJECTED, 0.0, f"No policy clause makes {label} reimbursable.", [])
    ent = policy.entitlement_for(category, employee.grade)
    if ent is None:
        c = _cite(policy.entitlements_for(category)[0])
        return decide(
            Outcome.REJECTED, 0.0, f"Grade {employee.grade} is not eligible to claim {label}. {_quoted(c)}", [c]
        )
    cites = [_cite(ent)]

    for rule in policy.age_rules:
        if date and (today - date).days > rule.max_age_days:
            c = _cite(rule)
            return decide(
                Outcome.REJECTED,
                0.0,
                f"The receipt is {(today - date).days} days old; the limit is {rule.max_age_days} days. {_quoted(c)}",
                [c],
            )

    limit = policy.limit_for(category, employee.grade)
    if limit is None:
        return decide(
            Outcome.APPROVED, claimed_inr, f"{label} is reimbursable with no amount limit. {_quoted(cites[0])}", cites
        )

    lc = _cite(limit)
    cites.append(lc)
    cap = to_inr(limit.amount, limit.currency) or limit.amount
    if limit.unit == "per_night":
        n = max(nights or 1, 1)
        cap, scope = cap * n, f"{inr(cap)} per night x {n}"
    else:
        scope = f"{inr(cap)} {limit.unit.replace('_', ' ')}"
    bucket = _bucket(limit, date)
    remaining = max(cap - tracker.used[bucket], 0.0) if bucket else cap

    if claimed_inr <= remaining + 0.005:
        if limit.requires_approval and not justification:
            return decide(
                Outcome.FLAGGED,
                0.0,
                f"{label} needs prior approval before it can be reimbursed. {_quoted(lc)}",
                cites,
                ["approval reference or justification"],
            )
        tracker.used[bucket] += claimed_inr
        return decide(Outcome.APPROVED, claimed_inr, f"Within the {scope} limit. {_quoted(lc)}", cites)

    over = claimed_inr - remaining
    if limit.over_limit_action == "partial":
        tracker.used[bucket] += remaining
        if remaining <= 0:
            return decide(Outcome.REJECTED, 0.0, f"The {scope} limit is already used up. {_quoted(lc)}", cites)
        return decide(
            Outcome.PARTIAL,
            remaining,
            f"The bill is {inr(claimed_inr)} but the limit is {scope}. Reimbursing {inr(remaining)}; "
            f"the excess {inr(over)} is not reimbursable. {_quoted(lc)}",
            cites,
        )
    if limit.over_limit_action == "needs_approval":
        if justification:
            tracker.used[bucket] += claimed_inr
            return decide(
                Outcome.APPROVED,
                claimed_inr,
                f"The bill is {inr(claimed_inr)}, above the {scope} limit; approved as an exception on "
                f"the recorded justification. {_quoted(lc)}",
                cites,
            )
        return decide(
            Outcome.FLAGGED,
            0.0,
            f"The bill is {inr(claimed_inr)}, above the {scope} limit. It can be reimbursed only as an "
            f"approved exception. {_quoted(lc)}",
            cites,
            ["manager-approved justification"],
        )
    return decide(
        Outcome.REJECTED,
        0.0,
        f"The bill is {inr(claimed_inr)}, above the {scope} limit, and the excess is not reimbursable. {_quoted(lc)}",
        cites,
    )
