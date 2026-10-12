"""Structured policy constraints produced by the LLM interpreter and enforced by code.

The LLM reads policy prose and fills these models. Nothing here contains policy
values: limits, grades and categories all come from the documents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Unit = Literal["per_receipt", "per_night", "per_day", "per_month"]
OverLimitAction = Literal["partial", "needs_approval", "reject"]


class Employee(BaseModel):
    id: str
    name: str
    grade: str
    role: str
    base_city: str


def load_employee(path: Path) -> Employee:
    return Employee.model_validate_json(path.read_text())


class CategoryDef(BaseModel):
    id: str = Field(description="short lowercase snake_case id, e.g. 'meals' or 'lodging'")
    label: str = Field(description="human-readable name")
    description: str = Field(description="what kinds of expenses belong in this category, per the policy")


class _Cited(BaseModel):
    clause: str = Field(description="clause number exactly as printed in the document, e.g. '2.1'")
    quote: str = Field(description="the words from that clause that support this item, copied verbatim")
    document: str = Field("", description="leave empty; filled in by the system")


class Entitlement(_Cited):
    category: str = Field(description="id of a category defined in `categories`")
    grades: list[str] = Field(
        description="every grade code allowed to claim the category, with grade bands expanded "
        "to individual codes using the document's own definitions"
    )


class Limit(_Cited):
    category: str
    amount: float
    currency: str = Field("INR", description="ISO 4217 code")
    unit: Unit
    grades: list[str] | None = Field(
        None, description="grade codes this limit applies to, or null when it applies to all grades"
    )
    over_limit_action: OverLimitAction = Field(
        description="partial: the policy reimburses up to the limit; needs_approval: above the limit "
        "only with a manager exception; reject: above the limit is not reimbursed"
    )
    requires_approval: bool = Field(
        False, description="true if the policy requires prior approval even when under the limit"
    )


class Exclusion(_Cited):
    category: str
    reason: str


class AgeRule(_Cited):
    max_age_days: int = Field(description="maximum age of a receipt, in days")


class PolicyConstraints(BaseModel):
    categories: list[CategoryDef] = Field(default_factory=list)
    entitlements: list[Entitlement] = Field(default_factory=list)
    limits: list[Limit] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)
    age_rules: list[AgeRule] = Field(default_factory=list)


class PolicySet(PolicyConstraints):
    """All interpreted documents merged. `documents` maps file name -> content hash."""

    documents: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def merge(cls, parts: list[tuple[str, str, PolicyConstraints]]) -> PolicySet:
        out = cls()
        seen: set[str] = set()
        for name, sha, c in parts:
            out.documents[name] = sha
            for cat in c.categories:
                if cat.id not in seen:
                    seen.add(cat.id)
                    out.categories.append(cat)
            out.entitlements += c.entitlements
            out.limits += c.limits
            out.exclusions += c.exclusions
            out.age_rules += c.age_rules
        return out

    def category_ids(self) -> set[str]:
        return {c.id for c in self.categories}

    def label(self, category: str) -> str:
        return next((c.label for c in self.categories if c.id == category), category)

    def exclusion_for(self, category: str) -> Exclusion | None:
        return next((x for x in self.exclusions if x.category == category), None)

    def entitlements_for(self, category: str) -> list[Entitlement]:
        return [e for e in self.entitlements if e.category == category]

    def entitlement_for(self, category: str, grade: str) -> Entitlement | None:
        return next((e for e in self.entitlements_for(category) if grade in e.grades), None)

    def limit_for(self, category: str, grade: str) -> Limit | None:
        """Grade-specific limits win over general ones."""
        candidates = [x for x in self.limits if x.category == category and (x.grades is None or grade in x.grades)]
        candidates.sort(key=lambda x: x.grades is None)
        return candidates[0] if candidates else None

    def eligible_categories(self, grade: str) -> list[str]:
        excluded = {x.category for x in self.exclusions}
        ids = {e.category for e in self.entitlements if grade in e.grades}
        return sorted(ids - excluded)
