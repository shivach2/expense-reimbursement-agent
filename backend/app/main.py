"""FastAPI app: upload receipts, review the AI-built claim, answer questions, submit to the mock finance system."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx2
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pydantic_ai.exceptions import ModelAPIError, UserError

from app import finance
from app.chat import run_chat
from app.config import ROOT
from app.ingest import IMAGE_EXTS, PDF_EXT, UnsupportedFileError, load_file
from app.policy.clauses import load_documents
from app.policy.interpreter import PolicyInterpretationError
from app.state import AppState, Session

MAX_FILES = 40
MAX_BYTES = 10 * 1024 * 1024
FRONTEND = ROOT / "frontend"
DEMO_DIR = ROOT / "data" / "synthetic" / "receipts"


class AnswerBody(BaseModel):
    kind: str
    target: str
    value: Any = ""


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class PolicyBody(BaseModel):
    text: str = Field(min_length=10, max_length=50_000)


def create_app(state: AppState | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.s = state or AppState(today=_env_today())
        yield

    app = FastAPI(title="Expense & Reimbursement Agent", lifespan=lifespan)

    def S() -> AppState:
        return app.state.s

    def session_or_404(sid: str) -> Session:
        s = S().get(sid)
        if s is None:
            raise HTTPException(404, "Unknown session")
        return s

    def llm_error(e: Exception) -> HTTPException:
        if isinstance(e, UserError):
            return HTTPException(503, f"The AI model is not configured: {e}")
        return HTTPException(502, f"The AI service failed: {type(e).__name__}: {str(e)[:200]}")

    # ---------------- sessions ----------------
    @app.post("/api/sessions")
    async def create_session():
        return S().snapshot(S().create_session())

    @app.get("/api/sessions/{sid}")
    async def get_session(sid: str):
        return S().snapshot(session_or_404(sid))

    @app.post("/api/sessions/{sid}/receipts", status_code=202)
    async def upload(sid: str, files: list[UploadFile] = File(...)):
        s, st = session_or_404(sid), S()
        if s.submitted_ref:
            raise HTTPException(409, "This claim was already submitted; start a new one")
        if s.status == "processing":
            raise HTTPException(409, "Still processing the previous upload")
        if len(files) > MAX_FILES:
            raise HTTPException(400, f"At most {MAX_FILES} files at a time")
        names = []
        for f in files:
            ext = Path(f.filename or "").suffix.lower()
            if ext not in IMAGE_EXTS | {PDF_EXT}:
                raise HTTPException(400, f"{f.filename}: only images and PDFs are supported")
            data = await f.read()
            if len(data) > MAX_BYTES:
                raise HTTPException(413, f"{f.filename}: larger than {MAX_BYTES // 1_000_000} MB")
            names.append(st.store_file(s, f.filename or "receipt" + ext, data))
        s.task = asyncio.create_task(st.process(s, names))
        s.status = "processing"
        return st.snapshot(s)

    @app.post("/api/sessions/{sid}/demo", status_code=202)
    async def load_demo(sid: str):
        """Load the bundled synthetic receipts (served from cached AI results when available)."""
        s, st = session_or_404(sid), S()
        if s.status == "processing":
            raise HTTPException(409, "Still processing")
        names = [st.store_file(s, p.name, p.read_bytes()) for p in sorted(DEMO_DIR.iterdir())]
        s.task = asyncio.create_task(st.process(s, names, use_cache=True))
        s.status = "processing"
        return st.snapshot(s)

    @app.get("/api/sessions/{sid}/thumb/{name}")
    async def thumb(sid: str, name: str):
        s = session_or_404(sid)
        path = s.files.get(name)
        if path is None:
            raise HTTPException(404, "Unknown file")
        try:
            page = load_file(path, max_side=500).pages[0]
        except UnsupportedFileError:
            raise HTTPException(415, "Cannot preview this file") from None
        return Response(page.data, media_type=page.media_type, headers={"Cache-Control": "max-age=3600"})

    @app.post("/api/sessions/{sid}/answers")
    async def answer(sid: str, body: AnswerBody):
        s = session_or_404(sid)
        if s.submitted_ref:
            raise HTTPException(409, "This claim was already submitted")
        try:
            S().apply_answer(s, body.kind, body.target, body.value)
        except (ValueError, TypeError) as e:
            raise HTTPException(422, str(e)) from e
        return S().snapshot(s)

    @app.post("/api/sessions/{sid}/chat")
    async def chat(sid: str, body: ChatBody):
        s = session_or_404(sid)
        if s.claim is None:
            raise HTTPException(409, "Upload receipts first")
        try:
            reply = await run_chat(S(), s, body.message)
        except (UserError, ModelAPIError, httpx2.TransportError) as e:
            raise llm_error(e) from e
        return {"reply": reply, "session": S().snapshot(s)}

    @app.post("/api/sessions/{sid}/submit")
    async def submit(sid: str):
        s = session_or_404(sid)
        if s.submitted_ref:
            raise HTTPException(409, f"Already submitted as {s.submitted_ref}")
        if s.claim is None:
            raise HTTPException(409, "Nothing to submit")
        try:
            result = finance.submit_claim(S().db_path, s.claim)
        except finance.NotSubmittable as e:
            raise HTTPException(409, str(e)) from e
        s.submitted_ref = result["id"]
        return {"submission": result, "session": S().snapshot(s)}

    # ---------------- policy ----------------
    def policy_view(policy) -> dict:
        docs = load_documents(S().policy_dir)
        return {
            "documents": [{"name": n, "text": t} for n, t in docs.items()],
            "interpreted": policy.model_dump(mode="json", exclude={"documents"}),
        }

    @app.get("/api/policy")
    async def get_policy():
        try:
            return policy_view(await S().policy())
        except (PolicyInterpretationError, UserError, ModelAPIError, httpx2.TransportError) as e:
            raise llm_error(e) from e

    @app.put("/api/policy/{name}")
    async def edit_policy(name: str, body: PolicyBody):
        """Edit a policy document; the AI re-interprets it and every claim is re-evaluated."""
        path = S().policy_dir / Path(name).name
        if not path.exists() or path.suffix != ".md":
            raise HTTPException(404, "Unknown policy document")
        old = path.read_text()
        path.write_text(body.text)
        try:
            policy = await S().reload_policy()
        except (PolicyInterpretationError, UserError, ModelAPIError, httpx2.TransportError) as e:
            path.write_text(old)  # keep the last good policy
            raise llm_error(e) from e
        return policy_view(policy)

    @app.post("/api/policy/reset")
    async def reset_policy():
        S().reset_policy_files()
        try:
            return policy_view(await S().reload_policy())
        except (PolicyInterpretationError, UserError, ModelAPIError, httpx2.TransportError) as e:
            raise llm_error(e) from e

    # ---------------- mock finance system ----------------
    @app.get("/api/finance/claims")
    async def finance_list():
        return finance.list_claims(S().db_path)

    @app.get("/api/finance/claims/{claim_id}")
    async def finance_get(claim_id: str):
        c = finance.get_claim(S().db_path, claim_id)
        if c is None:
            raise HTTPException(404, "Unknown claim")
        return c

    @app.get("/api/health")
    async def health():
        return {"ok": True, "model": S().settings.llm_model}

    if FRONTEND.exists():
        app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
    return app


def _env_today() -> dt.date | None:
    v = os.getenv("CLAIM_TODAY")
    return dt.date.fromisoformat(v) if v else None


app = create_app()
