"""LLM policy interpreter: policy prose in, grounded structured constraints out.

The model proposes constraints; deterministic code verifies each one is backed by
a verbatim quote from the clause it cites, and that every number it reports is
in that quote. Failures are fed back to the model (Pydantic AI `ModelRetry`).
Results are cached by document hash, so editing a policy document is all it
takes for new limits to apply: the next evaluation re-interprets it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior

from app.config import Settings, get_settings
from app.extraction import _run_with_backoff, _slug
from app.policy.clauses import load_documents, normalize, parse_clauses
from app.policy.schema import PolicyConstraints, PolicySet

INSTRUCTIONS = """\
You convert a corporate reimbursement policy document into structured constraints.
Rules:
- Use only what the document says. Never invent a limit, grade, or category.
- Every item must cite its clause number and a verbatim `quote` from that clause. A limit's
  amount must appear in its quote.
- Define a category for each kind of expense the document makes reimbursable or excludes. Use short
  lowercase snake_case ids. Reuse the ids you are given from other documents instead of creating
  near-duplicates.
- Expand grade bands (for example "Manager grades") into individual grade codes using the
  document's own definitions. If the document does not define the codes, leave grades empty.
- Choose `unit` from the wording: "per night", "per receipt", "per day", "per month".
- over_limit_action: "partial" if the document says the amount up to the limit is reimbursed;
  "needs_approval" if above the limit only with a manager exception; otherwise "reject".
- Put things the policy says are never reimbursable under `exclusions`, with a category for them.
- Do not output an item for clauses that contain no constraint.
"""


class PolicyInterpretationError(RuntimeError):
    pass


_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in _NUM_RE.findall(text)]


def grounding_problems(c: PolicyConstraints, clauses: dict[str, str]) -> list[str]:
    """Return a list of human-readable problems; empty means every item is grounded."""
    problems: list[str] = []
    known = {x.id for x in c.categories}

    def check(kind: str, item: Any) -> str | None:
        text = clauses.get(item.clause)
        if text is None:
            problems.append(f"{kind}: clause '{item.clause}' does not exist in the document")
            return None
        if normalize(item.quote) not in normalize(text):
            problems.append(f"{kind} {item.clause}: quote is not copied verbatim from that clause")
            return None
        return normalize(item.quote)

    def check_category(kind: str, item: Any) -> None:
        if item.category not in known:
            problems.append(f"{kind} {item.clause}: category '{item.category}' is not in `categories`")

    for e in c.entitlements:
        check("entitlement", e)
        check_category("entitlement", e)
    for x in c.exclusions:
        check("exclusion", x)
        check_category("exclusion", x)
    for lim in c.limits:
        q = check("limit", lim)
        check_category("limit", lim)
        if q is not None and not any(abs(n - lim.amount) < 1e-6 for n in _numbers(q)):
            problems.append(f"limit {lim.clause}: amount {lim.amount:g} does not appear in the quote")
    for a in c.age_rules:
        q = check("age rule", a)
        if q is not None and not any(abs(n - a.max_age_days) < 1e-6 for n in _numbers(q)):
            problems.append(f"age rule {a.clause}: {a.max_age_days} does not appear in the quote")
    return problems


def build_interpreter_agent(model: Any) -> Agent[dict[str, str], PolicyConstraints]:
    agent: Agent[dict[str, str], PolicyConstraints] = Agent(
        model,
        output_type=PolicyConstraints,
        deps_type=dict,
        instructions=INSTRUCTIONS,
        retries=3,
        defer_model_check=True,
    )

    @agent.output_validator
    def _grounded(ctx: RunContext[dict[str, str]], out: PolicyConstraints) -> PolicyConstraints:
        problems = grounding_problems(out, ctx.deps)
        if problems:
            raise ModelRetry("Fix these problems and return the full result again:\n- " + "\n- ".join(problems))
        return out

    return agent


def _cache_path(settings: Settings, key: str) -> Path:
    return settings.policy_cache_dir / _slug(settings.llm_model) / f"{key}.json"


async def interpret_document(
    name: str,
    text: str,
    *,
    known_categories: list[str] | None = None,
    agent: Any | None = None,
    settings: Settings | None = None,
) -> tuple[str, PolicyConstraints]:
    """Returns (content hash, constraints)."""
    settings = settings or get_settings()
    known = sorted(known_categories or [])
    sha = hashlib.sha256(text.encode()).hexdigest()
    key = hashlib.sha256(f"{sha}|{','.join(known)}".encode()).hexdigest()[:32]
    path = _cache_path(settings, key)
    if path.exists():
        return sha, PolicyConstraints.model_validate_json(path.read_text())

    clauses = {c.number: c.text for c in parse_clauses(name, text)}
    agent = agent or build_interpreter_agent(settings.llm_model)
    prompt = f"Document file name: {name}\n"
    if known:
        prompt += f"Category ids already defined by other documents (reuse them): {', '.join(known)}\n"
    prompt += f"\n--- DOCUMENT ---\n{text}"
    try:
        result = await _run_with_backoff(agent, prompt, deps=clauses)
    except UnexpectedModelBehavior as e:
        raise PolicyInterpretationError(f"Could not interpret {name}: {e}") from e

    constraints = result.output
    for items in (constraints.entitlements, constraints.limits, constraints.exclusions, constraints.age_rules):
        for item in items:
            item.document = name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(constraints.model_dump_json(indent=2))
    return sha, constraints


async def load_policy_set(
    policy_dir: Path,
    *,
    agent: Any | None = None,
    settings: Settings | None = None,
) -> PolicySet:
    """Interpret every policy document in the directory (cached) and merge the results."""
    settings = settings or get_settings()
    parts = []
    known: list[str] = []
    for name, text in load_documents(policy_dir).items():
        sha, constraints = await interpret_document(name, text, known_categories=known, agent=agent, settings=settings)
        known = sorted({*known, *(c.id for c in constraints.categories)})
        parts.append((name, sha, constraints))
    return PolicySet.merge(parts)
