"""Mock corporate reimbursement system (SQLite). Stands in for a real finance platform."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from app.claim import Claim, ClaimState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    employee_id TEXT NOT NULL,
    employee_name TEXT NOT NULL,
    grade TEXT NOT NULL,
    claimed_inr REAL NOT NULL,
    eligible_inr REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'submitted',
    payload TEXT NOT NULL
)
"""


class NotSubmittable(ValueError):
    pass


def _connect(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.execute(_SCHEMA)
    return conn


def submit_claim(db: Path, claim: Claim, *, now: dt.datetime | None = None) -> dict:
    """Store a READY claim and return its reference. Raises NotSubmittable otherwise."""
    if claim.state is not ClaimState.READY:
        raise NotSubmittable(f"Claim is {claim.state.value}; it must be ready before it can be submitted")
    now = now or dt.datetime.now()
    with _connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0] + 1
        ref = f"RMB-{now:%Y%m%d}-{n:04d}"
        conn.execute(
            "INSERT INTO claims "
            "(id, created_at, employee_id, employee_name, grade, claimed_inr, eligible_inr, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ref,
                now.isoformat(timespec="seconds"),
                claim.employee.id,
                claim.employee.name,
                claim.employee.grade,
                claim.claimed_inr,
                claim.eligible_inr,
                claim.model_dump_json(),
            ),
        )
    return {"id": ref, "created_at": now.isoformat(timespec="seconds"), "eligible_inr": claim.eligible_inr}


def list_claims(db: Path) -> list[dict]:
    with _connect(db) as conn:
        rows = conn.execute(
            "SELECT id, created_at, employee_id, employee_name, grade, claimed_inr, eligible_inr, status "
            "FROM claims ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_claim(db: Path, claim_id: str) -> dict | None:
    with _connect(db) as conn:
        row = conn.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if row is None:
        return None
    out = dict(row)
    out["payload"] = json.loads(out["payload"])
    return out
