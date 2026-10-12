"""AI expense classification into the employee's policy categories, with reasoning.

Text-only LLM call: it sees what was extracted from the bill plus the categories the
policy defines (and which of them this employee may claim). The category list comes
from the interpreted policy, so adding a category to a policy document needs no code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior

from app.config import Settings, get_settings
from app.extraction import _run_with_backoff, _slug
from app.models import ExtractedReceipt
from app.policy.schema import Employee, PolicySet

UNKNOWN = "unknown"

INSTRUCTIONS = """\
You classify one expense into a reimbursement category defined by the company's policy.
- Choose from the listed category ids only. Judge by what was actually bought (line items,
  vendor type), not by how the employee might want to claim it.
- Prefer a category the employee is eligible for when it genuinely fits; if the expense only fits a
  category that is excluded or unavailable to their grade, still choose that category so the
  policy can explain the outcome.
- Give a one or two sentence `reasoning` an employee can read.
- Set needs_clarification=true ONLY when the choice between categories would change what is
  reimbursed (different eligibility or limits) and the bill itself does not settle it, or when you
  cannot tell what was bought. Then pick the most likely category and ask one short question.
- Never ask about things collected elsewhere: the business purpose, the date, the amount, or taxes
  (a total above the sum of line items is normal tax), and never ask just to confirm an obvious category.
"""


class Classification(BaseModel):
    category: str = Field(description="id of one listed policy category")
    reasoning: str = Field(description="why this category fits this expense")
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    clarification_question: str | None = None


def unknown_classification(reason: str) -> Classification:
    return Classification(
        category=UNKNOWN,
        reasoning=reason,
        confidence=0.0,
        needs_clarification=True,
        clarification_question="What was this expense for?",
    )


def build_classifier_agent(model: Any) -> Agent[set[str], Classification]:
    agent: Agent[set[str], Classification] = Agent(
        model,
        output_type=Classification,
        deps_type=set,
        instructions=INSTRUCTIONS,
        retries=2,
        defer_model_check=True,
    )

    @agent.output_validator
    def _known(ctx: RunContext[set[str]], out: Classification) -> Classification:
        if out.category not in ctx.deps:
            raise ModelRetry(f"category must be one of: {', '.join(sorted(ctx.deps))}")
        return out

    return agent


def describe_categories(policy: PolicySet, employee: Employee) -> str:
    eligible = set(policy.eligible_categories(employee.grade))
    lines = []
    for c in policy.categories:
        if policy.exclusion_for(c.id):
            status = "never reimbursable"
        elif c.id in eligible:
            status = f"available to grade {employee.grade}"
        else:
            status = f"NOT available to grade {employee.grade}"
        lines.append(f"- {c.id}: {c.label}. {c.description} [{status}]")
    return "\n".join(lines)


def _prompt(e: ExtractedReceipt, employee: Employee, policy: PolicySet) -> str:
    r = e.receipt
    assert r is not None
    items = "; ".join(f"{i.description} ({i.amount})" for i in r.line_items) or "none listed"
    return (
        f"Employee: grade {employee.grade}, role {employee.role}, base city {employee.base_city}\n\n"
        f"Policy categories:\n{describe_categories(policy, employee)}\n\n"
        f"Expense:\n- vendor: {r.vendor}\n- date: {r.receipt_date}\n- total: {r.total} {r.currency}\n"
        f"- line items: {items}\n- extractor's description: {r.category}\n"
        f"- nights: {r.nights}\n- notes: {r.notes}\n"
    )


def _cache_path(settings: Settings, e: ExtractedReceipt, employee: Employee, policy: PolicySet) -> Path:
    key = hashlib.sha256(
        f"{e.file_sha256}|{sorted(policy.documents.items())}|{employee.grade}|{settings.llm_model}|{INSTRUCTIONS}".encode()
    ).hexdigest()[:32]
    return settings.classification_cache_dir / _slug(settings.llm_model) / f"{key}.json"


async def classify_receipt(
    e: ExtractedReceipt,
    employee: Employee,
    policy: PolicySet,
    *,
    agent: Any | None = None,
    settings: Settings | None = None,
) -> Classification:
    settings = settings or get_settings()
    if e.receipt is None or not e.receipt.readable:
        return unknown_classification("The bill could not be read.")

    path = _cache_path(settings, e, employee, policy)
    if path.exists():
        return Classification.model_validate_json(path.read_text())

    agent = agent or build_classifier_agent(settings.llm_model)
    try:
        result = await _run_with_backoff(agent, _prompt(e, employee, policy), deps=policy.category_ids())
    except UnexpectedModelBehavior:
        return unknown_classification("Automatic classification failed.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.output.model_dump_json(indent=2))
    return result.output
