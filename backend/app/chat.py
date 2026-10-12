"""Conversational assistant (agentic): answers questions about the claim and takes the employee's answers.

The agent never computes money or decides policy itself. It reads decisions the deterministic
engine already made (claim_status, explain_item), retrieves clauses from the policy documents
(search_policy, RAG), and records the employee's answers (record_answer), after which the claim
is rebuilt by code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai import Agent, RunContext

from app.claim import Claim, ClaimItem
from app.extraction import _run_with_backoff
from app.policy.clauses import ClauseIndex, load_documents, parse_clauses
from app.state import AppState, Session

INSTRUCTIONS = """\
You are an expense reimbursement assistant helping an employee turn their receipts into a claim.
- Facts come from tools. Never guess amounts, statuses or policy. Call claim_status, explain_item or
  search_policy before answering questions about them.
- When the employee gives information that answers an open question or corrects a receipt, record it
  with record_answer, then say what changed and what (if anything) is still needed.
- When you explain a decision, mention the policy clause reference (like TEP-2.1) and the amounts
  from the tool output. Say plainly what is eligible and what is not.
- Ask for only what is missing. Do not submit the claim; the employee presses Submit when it is ready.
- Be brief: at most five short sentences. Plain text only: no markdown, no asterisks, no headings,
  no bullet lists. Mention only the receipts the question is about.
"""


@dataclass
class ChatDeps:
    app: AppState
    session: Session


def _inr(x: float | None) -> str:
    return "n/a" if x is None else f"INR {x:,.2f}"


def summarise(claim: Claim) -> str:
    lines = [
        f"Claim state: {claim.state.value}. Claimed {_inr(claim.claimed_inr)}, eligible {_inr(claim.eligible_inr)}.",
        "Counts: " + ", ".join(f"{k}={v}" for k, v in claim.counts.items()),
    ]
    if claim.questions:
        lines.append("Open questions:")
        lines += [f"- [{q.kind}] target={q.target}: {q.text}" for q in claim.questions]
    else:
        lines.append("No open questions.")
    lines.append("Groups: " + "; ".join(f"{g.id} ({g.title})" for g in claim.groups))
    return "\n".join(lines)


def _resolve(session: Session, text: str) -> tuple[str | None, str]:
    """Match a receipt by file name or vendor. Returns (file, error message)."""
    q = text.strip().casefold()
    names = [e.source_file for e in session.extracted]
    hits = [n for n in names if n.casefold() == q] or [n for n in names if q and q in n.casefold()]
    if not hits and session.claim:
        hits = [i.file for i in session.claim.items if i.vendor and q and q in i.vendor.casefold()]
    if len(hits) == 1:
        return hits[0], ""
    if not hits:
        return None, f"No receipt matches '{text}'. Receipts: {', '.join(names)}"
    return None, f"'{text}' matches several receipts: {', '.join(hits)}. Which one?"


def describe_item(i: ClaimItem) -> str:
    out = [
        f"{i.file}: {i.vendor or 'unknown vendor'} on {i.receipt_date or 'unknown date'}, "
        f"{_inr(i.total_inr)} claimed, {_inr(i.eligible_inr)} eligible. Status: {i.status.value}.",
        f"Category: {i.category} (chosen by {i.category_source}). Why: {i.category_reasoning}",
    ]
    if i.decision:
        out.append(f"Decision: {i.decision.outcome.value}. {i.decision.explanation}")
        for c in i.decision.cites:
            out.append(f'Clause {c.ref} ({c.document}): "{c.quote}"')
        if i.decision.needs:
            out.append("Needs: " + ", ".join(i.decision.needs))
    out += [f"Note: {r}" for r in i.reasons if not i.decision or r != i.decision.explanation]
    return "\n".join(out)


def build_chat_agent(model: Any) -> Agent[ChatDeps, str]:
    agent: Agent[ChatDeps, str] = Agent(
        model, deps_type=ChatDeps, instructions=INSTRUCTIONS, retries=2, defer_model_check=True
    )

    @agent.instructions
    def _context(ctx: RunContext[ChatDeps]) -> str:
        e = ctx.deps.app.employee
        return f"The employee is {e.name}, grade {e.grade}, {e.role}, based in {e.base_city}."

    @agent.tool
    async def claim_status(ctx: RunContext[ChatDeps]) -> str:
        """Current claim state, totals, counts and the open questions."""
        c = ctx.deps.session.claim
        return summarise(c) if c else "No receipts have been processed yet."

    @agent.tool
    async def explain_item(ctx: RunContext[ChatDeps], receipt: str) -> str:
        """Explain one receipt's category, policy decision, clauses and eligible amount.
        `receipt` is a file name or vendor name (partial is fine)."""
        s = ctx.deps.session
        file, err = _resolve(s, receipt)
        if file is None or s.claim is None:
            return err or "No claim yet."
        return describe_item(next(i for i in s.claim.items if i.file == file))

    @agent.tool
    async def search_policy(ctx: RunContext[ChatDeps], query: str) -> str:
        """Search the policy documents and return the most relevant clauses with their references."""
        docs = load_documents(ctx.deps.app.policy_dir)
        index = ClauseIndex([c for name, text in docs.items() for c in parse_clauses(name, text)])
        hits = index.search(query, k=3)
        if not hits:
            return "No relevant policy clause found."
        return "\n".join(f"{c.ref} ({c.document}, {c.heading}): {c.text}" for c, _ in hits)

    @agent.tool
    async def record_answer(
        ctx: RunContext[ChatDeps],
        kind: Literal[
            "purpose_group",
            "purpose_item",
            "justification",
            "category",
            "vendor",
            "date",
            "amount",
            "currency",
            "confirm",
            "not_duplicate",
        ],
        target: str,
        value: str = "",
    ) -> str:
        """Record the employee's answer or correction, then return the updated claim summary.
        purpose_group: target is a group id (e.g. g-2026-09-14), value is the business purpose.
        purpose_item / justification / category / vendor / date (YYYY-MM-DD) / amount / currency:
        target is a receipt file or vendor name. confirm / not_duplicate: target is a receipt."""
        s, app = ctx.deps.session, ctx.deps.app
        if kind != "purpose_group":
            file, err = _resolve(s, target)
            if file is None:
                return err
            target = file
        try:
            app.apply_answer(s, kind, target, value)
        except ValueError as e:
            return f"Could not record that: {e}"
        return "Recorded.\n" + summarise(s.claim) if s.claim else "Recorded."

    return agent


async def run_chat(app: AppState, session: Session, message: str) -> str:
    if app.chat_agent is None:
        app.chat_agent = build_chat_agent(app.settings.llm_model)
    await app.policy()  # make sure categories are loaded for validation
    result = await _run_with_backoff(
        app.chat_agent, message, deps=ChatDeps(app, session), message_history=session.chat_history
    )
    session.chat_history = result.all_messages()
    return result.output
