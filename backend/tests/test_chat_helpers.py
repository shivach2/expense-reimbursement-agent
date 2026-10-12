"""Chat agent tools and helpers, driven by a scripted fake model (no LLM)."""

import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from app import chat
from app.chat import _resolve, build_chat_agent, describe_item, run_chat, summarise
from factories import make_state, session_with


@pytest.fixture
def state(tmp_path):
    return make_state(tmp_path)


def scripted(steps):
    """A fake model that calls the given (tool, args) steps in order, then answers 'ok'.
    `returns` always holds every tool result seen so far, in order."""
    remaining, returns = iter(steps), []

    def fn(messages, info):
        returns[:] = [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        step = next(remaining, None)
        part = TextPart("ok") if step is None else ToolCallPart(step[0], step[1])
        return ModelResponse(parts=[part])

    return FunctionModel(fn), returns


def chat_with(state, session, steps):
    model, returns = scripted(steps)
    state.chat_agent = build_chat_agent(model)
    assert asyncio.run(run_chat(state, session, "hello")) == "ok"
    return returns


def test_tools_before_any_receipts_give_helpful_answers(state):
    s = state.create_session()
    returns = chat_with(
        state, s, [("claim_status", {}), ("search_policy", {"query": "zzzz"}), ("explain_item", {"receipt": "nothing"})]
    )
    assert returns[0] == "No receipts have been processed yet."
    assert returns[1] == "No relevant policy clause found."
    assert "No receipt matches 'nothing'" in returns[2]


def test_search_policy_returns_clause_references(state):
    s = state.create_session()
    returns = chat_with(state, s, [("search_policy", {"query": "hotel limit per night"})])
    assert "TEP-2.1" in returns[0]


def test_record_answer_validation_messages_and_success(state):
    s = session_with(state, "r05", "r08")
    returns = chat_with(
        state,
        s,
        [
            ("record_answer", {"kind": "category", "target": "harbor", "value": "yachts"}),
            ("record_answer", {"kind": "confirm", "target": "ghost"}),
            ("record_answer", {"kind": "justification", "target": "harbor", "value": "Manager OK"}),
        ],
    )
    assert returns[0].startswith("Could not record that:") and "yachts" in returns[0]
    assert returns[1].startswith("No receipt matches")
    assert returns[2].startswith("Recorded.") and "Claim state" in returns[2]
    assert s.inputs.items["r08_foreign_usd.png"].justification == "Manager OK"


def test_explain_item_lists_clause_and_what_is_needed(state):
    s = session_with(state, "r08", "r05")
    returns = chat_with(state, s, [("explain_item", {"receipt": "r08"})])
    assert "Clause TEP-3.1" in returns[0] and "Needs: manager-approved justification" in returns[0]


def test_run_chat_builds_the_agent_lazily_and_keeps_history(state, monkeypatch):
    model, _ = scripted([])
    original = chat.build_chat_agent
    monkeypatch.setattr(chat, "build_chat_agent", lambda m: original(model))
    s = state.create_session()
    assert state.chat_agent is None
    asyncio.run(run_chat(state, s, "first"))
    first_len = len(s.chat_history)
    assert state.chat_agent is not None and first_len > 0
    asyncio.run(run_chat(state, s, "second"))
    assert len(s.chat_history) > first_len


def test_summary_and_receipt_resolution(state):
    s = session_with(state, "r05")
    assert "Claim state: needs_input" in summarise(s.claim) and "[purpose]" in summarise(s.claim)
    state.apply_answer(s, "purpose_group", s.claim.groups[0].id, "Restock")
    assert "No open questions." in summarise(s.claim)

    hotels = session_with(state, "r03", "r19")
    assert _resolve(hotels, "r03_hotel.pdf") == ("r03_hotel.pdf", "")
    file, err = _resolve(hotels, "lotus")
    assert file is None and "matches several receipts" in err
    assert describe_item(hotels.claim.items[0]).startswith("r03_hotel.pdf: Lotus Grove Hotel")
