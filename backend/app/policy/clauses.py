"""Split policy documents into numbered clauses and retrieve the relevant ones (RAG).

Retrieval is section-level BM25: offline, free, and enough for a policy library
of this size. Swapping in embeddings would only change `ClauseIndex.search`.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_CLAUSE_RE = re.compile(r"^(\d+\.\d+)\s+(.*\S)\s*$")
_HEADING_RE = re.compile(r"^##\s+(?:\d+\.\s*)?(.*\S)\s*$")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "an",
    "the",
    "of",
    "to",
    "for",
    "and",
    "or",
    "is",
    "are",
    "be",
    "in",
    "on",
    "by",
    "with",
    "as",
    "at",
    "it",
}


def doc_code(document: str) -> str:
    """travel_expense_policy -> TEP"""
    return "".join(w[0] for w in Path(document).stem.split("_") if w).upper()


def normalize(s: str) -> str:
    return " ".join(s.split()).casefold()


@dataclass(frozen=True)
class Clause:
    document: str
    number: str
    heading: str
    text: str

    @property
    def ref(self) -> str:
        return f"{doc_code(self.document)}-{self.number}"


def parse_clauses(document: str, text: str) -> list[Clause]:
    clauses: list[Clause] = []
    heading = ""
    cur: tuple[str, str, list[str]] | None = None

    def flush() -> None:
        nonlocal cur
        if cur:
            clauses.append(Clause(document, cur[0], cur[1], " ".join(cur[2])))
        cur = None

    for line in text.splitlines():
        if h := _HEADING_RE.match(line):
            flush()
            heading = h.group(1).strip()
        elif m := _CLAUSE_RE.match(line):
            flush()
            cur = (m.group(1), heading, [m.group(2)])
        elif cur and line.strip():
            cur[2].append(line.strip())
        else:
            flush()
    flush()
    return clauses


def load_documents(policy_dir: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in sorted(policy_dir.glob("*.md"))}


def _stem(t: str) -> str:
    """Strip a plural 's' so 'clients' matches 'client'."""
    return t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t


def _tokens(s: str) -> list[str]:
    return [_stem(t) for t in _TOKEN_RE.findall(s.casefold()) if t not in _STOP]


class ClauseIndex:
    def __init__(self, clauses: list[Clause], k1: float = 1.5, b: float = 0.75) -> None:
        self.clauses = clauses
        self.k1, self.b = k1, b
        self._docs = [Counter(_tokens(f"{c.heading} {c.text}")) for c in clauses]
        self._len = [sum(d.values()) for d in self._docs]
        self._avg = (sum(self._len) / len(self._len)) if self._len else 0.0
        df: Counter[str] = Counter()
        for d in self._docs:
            df.update(d.keys())
        n = len(clauses)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 3) -> list[tuple[Clause, float]]:
        q = _tokens(query)
        scored: list[tuple[Clause, float]] = []
        for clause, tf, length in zip(self.clauses, self._docs, self._len, strict=True):
            score = 0.0
            for t in q:
                if t in tf:
                    denom = tf[t] + self.k1 * (1 - self.b + self.b * length / (self._avg or 1))
                    score += self._idf[t] * tf[t] * (self.k1 + 1) / denom
            if score > 0:
                scored.append((clause, score))
        return sorted(scored, key=lambda x: -x[1])[:k]
