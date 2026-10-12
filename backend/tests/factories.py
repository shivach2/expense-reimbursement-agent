"""Shared builders for tests that need an AppState or a Session without calling any LLM."""

from __future__ import annotations

from app.classifier import Classification
from app.config import get_settings
from app.models import ExtractedReceipt
from app.state import AppState, Session
from test_claim import TODAY, load
from test_policy_evaluator import POLICY


def make_state(tmp_path, policy=POLICY) -> AppState:
    """An AppState with the fixture policy preloaded, so nothing needs the LLM or the policy cache."""
    state = AppState(get_settings(), runtime_dir=tmp_path, today=TODAY)
    state._policy = policy
    return state


def truth_for(*prefixes: str) -> tuple[list[ExtractedReceipt], dict[str, Classification]]:
    """Ground-truth extraction + classification for the synthetic receipts whose file name starts with a prefix."""
    extracted, classifications = load()
    keep = [e for e in extracted if e.source_file.startswith(prefixes)]
    return keep, {e.source_file: classifications[e.source_file] for e in keep}


def session_with(state: AppState, *prefixes: str) -> Session:
    """A ready session holding the chosen synthetic receipts and a built claim."""
    s = state.create_session()
    s.extracted, s.classifications = truth_for(*prefixes)
    state.rebuild(s)
    s.status = "ready"
    return s
