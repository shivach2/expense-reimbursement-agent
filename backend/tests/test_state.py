import asyncio

import pytest
from pydantic_ai.exceptions import UserError

from factories import make_state, session_with
from test_policy_evaluator import make_policy


@pytest.fixture
def state(tmp_path):
    return make_state(tmp_path)


def item(session, prefix):
    return next(i for i in session.claim.items if i.file.startswith(prefix))


def test_every_answer_kind_updates_the_claim(state):
    s = session_with(state, "r05", "r13")
    f = "r05_stationery.png"
    state.apply_answer(s, "vendor", f, " Paper Co ")
    assert item(s, "r05").vendor == "Paper Co"
    state.apply_answer(s, "amount", f, "300")
    assert item(s, "r05").total == 300.0
    state.apply_answer(s, "currency", f, "usd")
    assert item(s, "r05").currency == "USD" and item(s, "r05").total_inr == 300 * 83
    state.apply_answer(s, "purpose_item", f, "Restock")
    assert s.inputs.items[f].business_purpose == "Restock"
    state.apply_answer(s, "category", "r13_parking.png", "fuel")
    assert item(s, "r13").category == "fuel" and item(s, "r13").category_source == "employee"
    state.apply_answer(s, "confirm", f, "")
    state.apply_answer(s, "not_duplicate", f, "")
    assert s.inputs.items[f].confirmed and s.inputs.items[f].not_duplicate


def test_group_purpose_removes_the_purpose_question(state):
    s = session_with(state, "r05", "r13")
    purposes = [q for q in s.claim.questions if q.kind == "purpose"]
    assert len(purposes) == 2  # the two bills are more than 3 days apart: two groups
    for q in purposes:
        state.apply_answer(s, "purpose_group", q.target, "Office restock")
    assert s.claim.questions == [] and s.claim.state.value == "ready"


@pytest.mark.parametrize(
    "kind,target,value",
    [
        ("bogus", "r05_stationery.png", ""),
        ("purpose_group", "g-1999-01-01", "x"),
        ("confirm", "ghost.png", ""),
        ("date", "r05_stationery.png", "not-a-date"),
        ("amount", "r05_stationery.png", "abc"),
        ("category", "r05_stationery.png", "yachts"),
    ],
)
def test_invalid_answers_raise_value_errors(state, kind, target, value):
    s = session_with(state, "r05")
    with pytest.raises(ValueError):
        state.apply_answer(s, kind, target, value)


def test_category_answers_need_a_loaded_policy(state):
    s = session_with(state, "r05")
    state._policy = None
    with pytest.raises(ValueError):
        state.apply_answer(s, "category", "r05_stationery.png", "meals")


def test_store_file_avoids_name_collisions(state):
    s = state.create_session()
    names = [state.store_file(s, "a.png", b"1"), state.store_file(s, "a.png", b"2"), state.store_file(s, "a.png", b"3")]
    assert names == ["a.png", "a_2.png", "a_3.png"]
    assert state.store_file(s, "../../evil.png", b"x") == "evil.png"  # path components are dropped


def test_processing_errors_are_reported_not_swallowed(state, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.state.process_files", boom)
    s = state.create_session()
    state.store_file(s, "x.png", b"data")
    asyncio.run(state.process(s, ["x.png"]))
    assert s.status == "error" and s.error.startswith("RuntimeError: boom")


def test_rebuild_is_a_noop_without_policy_or_receipts(state):
    state._policy = None
    s = state.create_session()
    state.rebuild(s)
    assert s.claim is None


def test_snapshot_tolerates_a_missing_classification(state):
    s = session_with(state, "r05")
    s.classifications.clear()
    snap = state.snapshot(s)
    assert snap["receipts"]["r05_stationery.png"]["classification"] is None
    assert snap["receipts"]["r05_stationery.png"]["thumb"].endswith("/thumb/r05_stationery.png")


def test_reloading_the_policy_recomputes_existing_claims(state, monkeypatch):
    s = session_with(state, "r03", "r19")
    assert s.claim.eligible_inr == 10000  # two hotel bills, each capped at 5,000

    async def load_changed_policy(*a, **k):
        return make_policy(hotel_cap=7000)

    monkeypatch.setattr("app.state.load_policy_set", load_changed_policy)
    asyncio.run(state.reload_policy())
    assert s.claim.eligible_inr == pytest.approx(7000 + 6496)


def test_a_missing_api_key_is_reported_in_plain_words(state, monkeypatch):
    async def no_key(*a, **k):
        raise UserError("Set the ANTHROPIC_API_KEY environment variable")

    monkeypatch.setattr("app.state.process_files", no_key)
    s = state.create_session()
    state.store_file(s, "x.png", b"data")
    asyncio.run(state.process(s, ["x.png"]))
    assert s.status == "error" and s.error.startswith("The AI model is not configured")
