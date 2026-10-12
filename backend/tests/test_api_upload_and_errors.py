"""API tests for the upload path and every error branch. The extraction/classification pipeline is replaced by a
fake that returns ground truth, so no LLM, cache or network is involved."""

import datetime as dt
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.exceptions import ModelHTTPError, UserError

from app.main import MAX_BYTES, MAX_FILES, _env_today, create_app
from app.policy.interpreter import PolicyInterpretationError
from factories import make_state, truth_for

RECEIPTS = Path(__file__).resolve().parents[2] / "data" / "synthetic" / "receipts"


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = make_state(tmp_path)
    extracted, classifications = truth_for("r05", "r13", "r08")

    async def fake_process_files(paths, employee, policy, *, settings=None, concurrency=4, on_progress=None):
        out, classes = [], {}
        for p in paths:
            src = next(e for e in extracted if p.name.startswith(Path(e.source_file).stem))
            out.append(src.model_copy(update={"source_file": p.name}))
            classes[p.name] = classifications[src.source_file]
            if on_progress:
                on_progress()
        return out, classes

    monkeypatch.setattr("app.state.process_files", fake_process_files)
    with TestClient(create_app(state)) as c:
        c.state = state
        yield c


def upload(client, sid, *names):
    files = [("files", (n, (RECEIPTS / n).read_bytes(), "image/png")) for n in names]
    return client.post(f"/api/sessions/{sid}/receipts", files=files)


def wait_ready(client, sid, timeout=10):
    t = time.time()
    while time.time() - t < timeout:
        snap = client.get(f"/api/sessions/{sid}").json()
        if snap["status"] in ("ready", "error"):
            return snap
        time.sleep(0.05)
    raise AssertionError("processing timed out")


def new_session(client):
    return client.post("/api/sessions").json()["id"]


def test_upload_processes_files_and_builds_a_claim(client):
    sid = new_session(client)
    r = upload(client, sid, "r05_stationery.png", "r13_parking.png")
    assert r.status_code == 202 and r.json()["status"] == "processing"
    snap = wait_ready(client, sid)
    assert snap["status"] == "ready"
    assert [i["file"] for i in snap["claim"]["items"]] == ["r05_stationery.png", "r13_parking.png"]
    assert snap["progress"] == {"done": 2, "total": 2}
    assert client.get(snap["receipts"]["r05_stationery.png"]["thumb"]).status_code == 200


def test_uploading_the_same_name_twice_keeps_both_files(client):
    sid = new_session(client)
    upload(client, sid, "r05_stationery.png")
    wait_ready(client, sid)
    upload(client, sid, "r05_stationery.png")
    snap = wait_ready(client, sid)
    assert set(snap["receipts"]) == {"r05_stationery.png", "r05_stationery_2.png"}


def test_too_many_files_are_rejected(client):
    sid = new_session(client)
    files = [("files", (f"a{i}.png", b"x", "image/png")) for i in range(MAX_FILES + 1)]
    r = client.post(f"/api/sessions/{sid}/receipts", files=files)
    assert r.status_code == 400 and "At most" in r.json()["detail"]


def test_oversized_file_is_rejected(client):
    sid = new_session(client)
    r = client.post(
        f"/api/sessions/{sid}/receipts", files=[("files", ("big.png", b"x" * (MAX_BYTES + 1), "image/png"))]
    )
    assert r.status_code == 413


def test_upload_and_demo_are_refused_while_processing(client):
    sid = new_session(client)
    client.state.get(sid).status = "processing"
    assert upload(client, sid, "r05_stationery.png").status_code == 409
    assert client.post(f"/api/sessions/{sid}/demo").status_code == 409


def test_upload_is_refused_after_submission(client):
    sid = new_session(client)
    client.state.get(sid).submitted_ref = "RMB-1"
    assert upload(client, sid, "r05_stationery.png").status_code == 409


def test_thumbnail_of_an_unreadable_file_is_415(client):
    sid = new_session(client)
    client.state.store_file(client.state.get(sid), "bad.png", b"not an image")
    assert client.get(f"/api/sessions/{sid}/thumb/bad.png").status_code == 415
    assert client.get(f"/api/sessions/{sid}/thumb/never-uploaded.png").status_code == 404


def test_submitting_an_empty_session_is_409(client):
    sid = new_session(client)
    r = client.post(f"/api/sessions/{sid}/submit")
    assert r.status_code == 409 and r.json()["detail"] == "Nothing to submit"


def test_chat_ai_failures_map_to_http_errors(client, monkeypatch):
    sid = new_session(client)
    upload(client, sid, "r05_stationery.png")
    wait_ready(client, sid)

    async def no_key(*a, **k):
        raise UserError("no API key")

    async def overloaded(*a, **k):
        raise ModelHTTPError(500, "m", body=None)

    monkeypatch.setattr("app.main.run_chat", no_key)
    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"})
    assert r.status_code == 503 and "not configured" in r.json()["detail"]
    monkeypatch.setattr("app.main.run_chat", overloaded)
    r = client.post(f"/api/sessions/{sid}/chat", json={"message": "hi"})
    assert r.status_code == 502 and "ModelHTTPError" in r.json()["detail"]


def test_policy_view_failures_are_reported(client, monkeypatch):
    async def broken():
        raise PolicyInterpretationError("could not interpret")

    monkeypatch.setattr(client.state, "policy", broken)
    r = client.get("/api/policy")
    assert r.status_code == 502 and "PolicyInterpretationError" in r.json()["detail"]


def test_failed_policy_edit_restores_the_previous_text(client, monkeypatch):
    path = client.state.policy_dir / "travel_expense_policy.md"
    original = path.read_text()

    async def no_key():
        raise UserError("no API key")

    monkeypatch.setattr(client.state, "reload_policy", no_key)
    r = client.put("/api/policy/travel_expense_policy.md", json={"text": original.replace("5,000", "9,000")})
    assert r.status_code == 503
    assert path.read_text() == original


def test_failed_policy_reset_is_reported(client, monkeypatch):
    async def overloaded():
        raise ModelHTTPError(503, "m", body=None)

    monkeypatch.setattr(client.state, "reload_policy", overloaded)
    assert client.post("/api/policy/reset").status_code == 502


def test_unknown_finance_claim_is_404_and_health_reports_the_model(client):
    assert client.get("/api/finance/claims/RMB-0").status_code == 404
    health = client.get("/api/health").json()
    assert health["ok"] is True and health["model"]


def test_claim_today_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("CLAIM_TODAY", "2026-10-12")
    assert _env_today() == dt.date(2026, 10, 12)
    monkeypatch.delenv("CLAIM_TODAY")
    assert _env_today() is None
