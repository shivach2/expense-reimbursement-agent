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
