"""API tests. They run offline: AI results come from the committed caches (the demo fallback path),
and the chat agent is a scripted fake model."""

import datetime as dt
import time

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.chat import build_chat_agent
from app.config import get_settings
from app.extraction import _slug
from app.main import create_app
from app.state import AppState

TODAY = dt.date(2026, 10, 12)


def caches_are_warm(settings) -> bool:
    """True when extraction, policy and classification results exist for the configured model."""
    slug = _slug(settings.llm_model)
    dirs = (settings.cache_dir, settings.policy_cache_dir, settings.classification_cache_dir)
    return all(any((d / slug).glob("*.json")) for d in dirs)


@pytest.fixture
def client(tmp_path):
    # Uses LLM_MODEL from the environment/.env. These tests replay AI results from data/cache, so they are skipped
    # (not failed) on a cold checkout; warm the caches once with the same model:
    #   python tools/run_pipeline.py --today 2026-10-12
    settings = get_settings()
    if not caches_are_warm(settings):
        pytest.skip("AI caches are cold for this LLM_MODEL; run `python tools/run_pipeline.py --today 2026-10-12` once")
    state = AppState(settings, runtime_dir=tmp_path, today=TODAY)
    with TestClient(create_app(state)) as c:
        c.state = state
        yield c


def wait_ready(client, sid, timeout=60):
    t = time.time()
    while time.time() - t < timeout:
        snap = client.get(f"/api/sessions/{sid}").json()
        if snap["status"] in ("ready", "error"):
            return snap
        time.sleep(0.2)
    raise AssertionError("processing timed out")


def demo_session(client):
    sid = client.post("/api/sessions").json()["id"]
    assert client.post(f"/api/sessions/{sid}/demo").status_code == 202
    snap = wait_ready(client, sid)
    assert snap["status"] == "ready", snap["error"]
    return sid, snap


def answer_everything(client, sid, snap):
    for q in snap["claim"]["questions"]:
        kind = {
            "purpose": "purpose_group",
            "justify": "justification",
            "field": "date",
            "clarify": "confirm",
            "confirm": "confirm",
        }[q["kind"]]
        value = {"purpose_group": "Customer visit", "justification": "Manager approved", "date": "2026-09-17"}.get(
            kind, ""
        )
        r = client.post(f"/api/sessions/{sid}/answers", json={"kind": kind, "target": q["target"], "value": value})
        assert r.status_code == 200, r.text
        snap = r.json()
    return snap


def test_demo_receipts_become_a_claim_with_decisions(client):
    sid, snap = demo_session(client)
    claim = snap["claim"]
    assert claim["state"] == "needs_input"
    assert claim["counts"]["duplicate"] == 3
    assert claim["eligible_inr"] < claim["claimed_inr"]
    hotel = next(i for i in claim["items"] if i["file"].startswith("r03"))
    assert hotel["decision"]["outcome"] == "partial" and hotel["decision"]["cites"][-1]["ref"] == "TEP-2.1"
    assert snap["receipts"]["r03_hotel.pdf"]["thumb"].endswith("/thumb/r03_hotel.pdf")


def test_thumbnails_are_served_for_images_and_pdfs(client):
    sid, _ = demo_session(client)
    for name in ("r01_cafe.png", "r03_hotel.pdf"):
        r = client.get(f"/api/sessions/{sid}/thumb/{name}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/sessions/{sid}/thumb/../../etc/passwd").status_code == 404


def test_answering_then_submitting_reaches_the_mock_finance_system(client):
    sid, snap = demo_session(client)
    early = client.post(f"/api/sessions/{sid}/submit")
    assert early.status_code == 409  # not ready yet

    snap = answer_everything(client, sid, snap)
    assert snap["claim"]["state"] == "ready", snap["claim"]["questions"]
    r = client.post(f"/api/sessions/{sid}/submit")
    assert r.status_code == 200
    ref = r.json()["submission"]["id"]
    assert ref.startswith("RMB-")

    rows = client.get("/api/finance/claims").json()
    assert [x["id"] for x in rows] == [ref]
    stored = client.get(f"/api/finance/claims/{ref}").json()
    assert stored["payload"]["state"] == "ready" and stored["eligible_inr"] == snap["claim"]["eligible_inr"]
    assert client.post(f"/api/sessions/{sid}/submit").status_code == 409  # no double submit
    assert (
        client.post(f"/api/sessions/{sid}/answers", json={"kind": "confirm", "target": "r01_cafe.png"}).status_code
        == 409
    )


def test_bad_inputs_are_rejected(client):
    sid = client.post("/api/sessions").json()["id"]
    assert (
        client.post(f"/api/sessions/{sid}/receipts", files=[("files", ("notes.txt", b"hi", "text/plain"))]).status_code
        == 400
    )
    assert client.post("/api/sessions/nope/demo").status_code == 404
    sid, snap = demo_session(client)
    for body in (
        {"kind": "bogus", "target": "r01_cafe.png"},
        {"kind": "category", "target": "r01_cafe.png", "value": "yachts"},
        {"kind": "date", "target": "r01_cafe.png", "value": "not-a-date"},
        {"kind": "confirm", "target": "ghost.png"},
    ):
        assert client.post(f"/api/sessions/{sid}/answers", json=body).status_code == 422


def test_editing_the_policy_document_changes_the_claim_without_code(client):
    sid, before = demo_session(client)
    doc = next(d for d in client.get("/api/policy").json()["documents"] if d["name"] == "travel_expense_policy.md")
    assert "INR 5,000 per night" in doc["text"]

    new = client.put(
        "/api/policy/travel_expense_policy.md",
        json={"text": doc["text"].replace("INR 5,000 per night", "INR 7,000 per night")},
    )
    assert new.status_code == 200, new.text
    lodging = next(x for x in new.json()["interpreted"]["limits"] if x["category"] == "lodging")
    assert lodging["amount"] == 7000

    after = client.get(f"/api/sessions/{sid}").json()["claim"]
    assert after["eligible_inr"] > before["claim"]["eligible_inr"]
    assert next(i for i in after["items"] if i["file"].startswith("r19"))["decision"]["outcome"] == "approved"

    assert client.post("/api/policy/reset").status_code == 200
    reset = client.get(f"/api/sessions/{sid}").json()["claim"]
    assert reset["eligible_inr"] == before["claim"]["eligible_inr"]


def test_unknown_policy_document_is_404(client):
    assert client.put("/api/policy/missing.md", json={"text": "x" * 20}).status_code == 404


def scripted_chat(client, steps):
    """steps: list of (tool name, args) the fake model will call in order, then it replies 'Done'."""
    calls, returns = iter(steps), []

    def fn(messages, info: AgentInfo):
        returns[:] = [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)]
        nxt = next(calls, None)
        if nxt is None:
            return ModelResponse(parts=[TextPart("Done")])
        return ModelResponse(parts=[ToolCallPart(nxt[0], nxt[1])])

    client.state.chat_agent = build_chat_agent(FunctionModel(fn))
    return returns


def test_chat_agent_explains_with_clauses_and_records_answers(client):
    sid, snap = demo_session(client)
    group = snap["claim"]["groups"][-1]["id"]
    returns = scripted_chat(
        client,
        [
            ("explain_item", {"receipt": "lotus"}),  # two hotels -> ambiguous
            ("explain_item", {"receipt": "r03"}),
            ("search_policy", {"query": "hotel limit per night"}),
            ("record_answer", {"kind": "purpose_group", "target": group, "value": "Customer visit"}),
        ],
    )
    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "why was my hotel cut?"})
    assert r.status_code == 200 and r.json()["reply"] == "Done"
    assert "matches several receipts" in returns[0]
    assert "TEP-2.1" in returns[1] and "INR 5,000" in returns[1]
    assert "TEP-2.1" in returns[2]  # retrieval found the hotel clause
    assert client.state.sessions[sid].inputs.group_purposes[group] == "Customer visit"
    assert not any(q["kind"] == "purpose" and q["target"] == group for q in r.json()["session"]["claim"]["questions"])


def test_chat_needs_receipts_first(client):
    sid = client.post("/api/sessions").json()["id"]
    assert client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"}).status_code == 409
