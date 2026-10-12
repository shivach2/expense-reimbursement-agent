"""In-memory application state: policy, employee, and per-upload claim sessions."""

from __future__ import annotations

import asyncio
import datetime as dt
import shutil
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from pydantic_ai.exceptions import UserError

from app.claim import Claim, ClaimInputs, ItemInput, build_claim
from app.classifier import Classification
from app.config import ROOT, Settings, get_settings
from app.models import ExtractedReceipt
from app.pipeline import process_files
from app.policy.interpreter import load_policy_set
from app.policy.schema import Employee, PolicySet, load_employee

ANSWER_KINDS = (
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
)


@dataclass
class Session:
    id: str
    dir: Path
    files: dict[str, Path] = field(default_factory=dict)  # name -> stored path
    extracted: list[ExtractedReceipt] = field(default_factory=list)
    classifications: dict[str, Classification] = field(default_factory=dict)
    inputs: ClaimInputs = field(default_factory=ClaimInputs)
    claim: Claim | None = None
    status: str = "idle"  # idle | processing | ready | error
    done: int = 0
    total: int = 0
    error: str | None = None
    submitted_ref: str | None = None
    chat_history: list[Any] = field(default_factory=list)
    task: asyncio.Task | None = None


class AppState:
    def __init__(
        self, settings: Settings | None = None, *, runtime_dir: Path | None = None, today: dt.date | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.runtime = runtime_dir or ROOT / "backend" / "runtime"
        self.policy_dir = self.runtime / "policies"
        self.uploads = self.runtime / "uploads"
        self.db_path = self.runtime / "finance.sqlite"
        self.today = today
        self.employee: Employee = load_employee(self.settings.employee_path)
        self.sessions: dict[str, Session] = {}
        self._policy: PolicySet | None = None
        self._policy_lock = asyncio.Lock()
        self.chat_agent: Any = None
        self.reset_policy_files()

    # ---- policy ----
    def reset_policy_files(self) -> None:
        self.policy_dir.mkdir(parents=True, exist_ok=True)
        for p in self.settings.policy_dir.glob("*.md"):
            shutil.copyfile(p, self.policy_dir / p.name)
        self._policy = None

    async def policy(self) -> PolicySet:
        async with self._policy_lock:
            if self._policy is None:
                self._policy = await load_policy_set(self.policy_dir, settings=self.settings)
            return self._policy

    async def reload_policy(self) -> PolicySet:
        """Re-interpret the policy documents (cached by hash) and re-evaluate every claim."""
        async with self._policy_lock:
            self._policy = await load_policy_set(self.policy_dir, settings=self.settings)
            policy = self._policy
        for s in self.sessions.values():
            self.rebuild(s, policy)
        return policy

    # ---- sessions ----
    def create_session(self) -> Session:
        sid = uuid.uuid4().hex[:12]
        s = Session(id=sid, dir=self.uploads / sid)
        s.dir.mkdir(parents=True, exist_ok=True)
        self.sessions[sid] = s
        return s

    def get(self, sid: str) -> Session | None:
        return self.sessions.get(sid)

    def rebuild(self, s: Session, policy: PolicySet | None = None) -> None:
        policy = policy or self._policy
        if policy is None or not s.extracted:
            return
        s.claim = build_claim(
            s.extracted, s.classifications, self.employee, policy, s.inputs, today=self.today or dt.date.today()
        )

    def store_file(self, s: Session, name: str, data: bytes) -> str:
        name = Path(name).name or "receipt"
        stem, suffix = Path(name).stem, Path(name).suffix
        final, n = name, 1
        while final in s.files:
            n += 1
            final = f"{stem}_{n}{suffix}"
        path = s.dir / final
        path.write_bytes(data)
        s.files[final] = path
        return final

    async def process(self, s: Session, names: list[str], *, use_cache: bool = False) -> None:
        settings = replace(self.settings, use_extraction_cache=True) if use_cache else self.settings
        s.status, s.error = "processing", None
        s.total += len(names)
        try:
            policy = await self.policy()

            def tick() -> None:
                s.done += 1

            extracted, cls = await process_files(
                [s.files[n] for n in names], self.employee, policy, settings=settings, on_progress=tick
            )
            s.extracted.extend(extracted)
            s.classifications.update(cls)
            self.rebuild(s, policy)
            s.status = "ready"
        except UserError as e:  # no API key / provider not configured: say so plainly
            s.status, s.error = "error", f"The AI model is not configured: {str(e)[:200]}"
        except Exception as e:  # surfaced to the UI instead of a silent hang
            s.status, s.error = "error", f"{type(e).__name__}: {str(e)[:300]}"

    # ---- answering ----
    def apply_answer(self, s: Session, kind: str, target: str, value: Any) -> None:
        if kind not in ANSWER_KINDS:
            raise ValueError(f"unknown answer kind '{kind}'")
        if kind == "purpose_group":
            if s.claim is None or target not in {g.id for g in s.claim.groups}:
                raise ValueError(f"unknown group '{target}'")
            s.inputs.group_purposes[target] = str(value).strip()
        else:
            if target not in {e.source_file for e in s.extracted}:
                raise ValueError(f"unknown receipt '{target}'")
            item = s.inputs.items.setdefault(target, ItemInput())
            if kind == "purpose_item":
                item.business_purpose = str(value).strip()
            elif kind == "justification":
                item.justification = str(value).strip()
            elif kind == "category":
                if self._policy is None or str(value) not in self._policy.category_ids():
                    raise ValueError(f"'{value}' is not a policy category")
                item.category = str(value)
            elif kind == "vendor":
                item.vendor = str(value).strip()
            elif kind == "date":
                item.receipt_date = dt.date.fromisoformat(str(value))
            elif kind == "amount":
                item.total = float(value)
            elif kind == "currency":
                item.currency = str(value).strip().upper()
            elif kind == "confirm":
                item.confirmed = True
            elif kind == "not_duplicate":
                item.not_duplicate = True
        self.rebuild(s)

    # ---- serialisation ----
    def snapshot(self, s: Session) -> dict:
        receipts = {}
        cls = s.classifications
        for e in s.extracted:
            receipts[e.source_file] = {
                "extracted": e.model_dump(mode="json", exclude={"file_sha256"}),
                "classification": cls[e.source_file].model_dump(mode="json") if e.source_file in cls else None,
                "thumb": f"/api/sessions/{s.id}/thumb/{e.source_file}",
            }
        return {
            "id": s.id,
            "status": s.status,
            "error": s.error,
            "progress": {"done": s.done, "total": s.total},
            "submitted_ref": s.submitted_ref,
            "employee": self.employee.model_dump(),
            "claim": s.claim.model_dump(mode="json") if s.claim else None,
            "receipts": receipts,
        }
