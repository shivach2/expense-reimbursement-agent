# A1 — verbatim source: backend/app

Create every file below at the given path with **exactly** the content between the fences (the fence lines themselves are not part of the file). Each file ends with a single trailing newline. Do not change anything. Create missing folders as needed. A file marked `(empty file)` must be created empty. Some fences are four backticks long because the file itself contains three-backtick code blocks; the fence that closes a file has the same length as the one that opened it.

### FILE: backend/app/__init__.py  *(empty file)*

```python
```

### FILE: backend/app/config.py  (35 lines)

```python
"""Runtime settings, read from environment / .env at the repo root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    llm_model: str
    llm_call_delay_s: float
    use_extraction_cache: bool
    cache_dir: Path
    policy_cache_dir: Path = ROOT / "data" / "cache" / "policy"
    classification_cache_dir: Path = ROOT / "data" / "cache" / "classification"
    policy_dir: Path = ROOT / "data" / "policies"
    employee_path: Path = ROOT / "data" / "employees" / "emp_demo_m2.json"
    max_image_side: int = 1600
    max_pdf_pages: int = 3


def get_settings() -> Settings:
    return Settings(
        llm_model=os.getenv("LLM_MODEL", "anthropic:claude-sonnet-5-5"),
        llm_call_delay_s=float(os.getenv("LLM_CALL_DELAY_S", "0")),
        use_extraction_cache=os.getenv("USE_EXTRACTION_CACHE", "false").lower() == "true",
        cache_dir=ROOT / "data" / "cache" / "extractions",
    )
```

### FILE: backend/app/models.py  (64 lines)

```python
"""Pydantic schemas for receipt extraction.

`Receipt` is the schema the LLM must fill in. `ExtractedReceipt` wraps it with
file metadata and review status produced by our own code.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    description: str
    amount: float | None = None


class FieldConfidence(BaseModel):
    vendor: float = Field(ge=0, le=1, description="0-1 confidence the vendor name is correct")
    date: float = Field(ge=0, le=1, description="0-1 confidence the date is correct (0 if absent)")
    total: float = Field(ge=0, le=1, description="0-1 confidence the total is correct")


class Receipt(BaseModel):
    readable: bool = Field(description="False if the image is not a receipt or is unreadable")
    vendor: str | None = Field(None, description="Merchant name as printed")
    receipt_date: dt.date | None = Field(
        None,
        description="Date on the receipt as ISO YYYY-MM-DD. Printed dates are day-first "
        "(DD/MM/YYYY). Null if no date is visible; never guess.",
    )
    total: float | None = Field(None, description="Final amount paid, including tax")
    tax: float | None = Field(None, description="Total tax amount, null if not shown")
    currency: str = Field(description="ISO 4217 code, e.g. INR, USD, SGD. Rs means INR.")
    category: str = Field(
        description="Short free-text description of the kind of expense, e.g. 'restaurant meal', "
        "'taxi ride', 'hotel stay', 'petrol'. This is only a hint; policy categories are assigned later."
    )
    nights: int | None = Field(None, description="Number of nights for a hotel stay, otherwise null")
    line_items: list[LineItem] = Field(default_factory=list)
    receipt_number: str | None = Field(None, description="Bill / invoice number if printed")
    payment_method: str | None = Field(None, description="e.g. CARD, CASH, UPI, if shown")
    confidence: FieldConfidence
    notes: str | None = Field(None, description="Anything unusual worth a human's attention")

    @field_validator("currency")
    @classmethod
    def _currency_code(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO 4217 code")
        return v


class ExtractedReceipt(BaseModel):
    source_file: str
    file_sha256: str
    model: str
    receipt: Receipt | None = None
    total_inr: float | None = None
    needs_review: bool = True
    review_reasons: list[str] = Field(default_factory=list)
    error: str | None = None
```

### FILE: backend/app/currency.py  (21 lines)

```python
"""Static, illustrative FX rates to INR (prototype only, not live market data)."""

from __future__ import annotations

RATES_TO_INR: dict[str, float] = {
    "INR": 1.0,
    "USD": 83.0,
    "EUR": 90.0,
    "GBP": 105.0,
    "SGD": 62.0,
    "AED": 22.6,
}


def is_supported(currency: str) -> bool:
    return currency.upper() in RATES_TO_INR


def to_inr(amount: float, currency: str) -> float | None:
    rate = RATES_TO_INR.get(currency.upper())
    return None if rate is None else round(amount * rate, 2)
```

### FILE: backend/app/ingest.py  (78 lines)

```python
"""Load receipt files (images / PDFs) into normalised page images for the LLM.

Re-encoding to JPEG drops EXIF/GPS metadata, which keeps location data out of
LLM requests and caches.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
PDF_EXT = ".pdf"


class UnsupportedFileError(ValueError):
    pass


@dataclass(frozen=True)
class Page:
    data: bytes
    media_type: str = "image/jpeg"


@dataclass(frozen=True)
class LoadedFile:
    name: str
    sha256: str
    pages: list[Page]
    embedded_text: str = field(default="")


def _to_page(img: Image.Image, max_side: int) -> Page:
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return Page(buf.getvalue())


def load_bytes(data: bytes, filename: str, *, max_side: int = 1600, max_pdf_pages: int = 3) -> LoadedFile:
    ext = Path(filename).suffix.lower()
    sha = hashlib.sha256(data).hexdigest()

    if ext in IMAGE_EXTS:
        try:
            with Image.open(io.BytesIO(data)) as img:
                pages = [_to_page(img, max_side)]
        except OSError as e:
            raise UnsupportedFileError(f"{filename}: not a readable image ({e})") from e
        return LoadedFile(filename, sha, pages)

    if ext == PDF_EXT:
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as e:  # pymupdf raises several error types
            raise UnsupportedFileError(f"{filename}: not a readable PDF ({e})") from e
        pages: list[Page] = []
        texts: list[str] = []
        with doc:
            for page in list(doc)[:max_pdf_pages]:
                pix = page.get_pixmap(dpi=150)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                pages.append(_to_page(img, max_side))
                texts.append(page.get_text().strip())
        return LoadedFile(filename, sha, pages, "\n".join(t for t in texts if t))

    raise UnsupportedFileError(f"{filename}: unsupported type '{ext}'")


def load_file(path: Path, **kwargs) -> LoadedFile:
    return load_bytes(path.read_bytes(), path.name, **kwargs)
```

### FILE: backend/app/quality.py  (41 lines)

```python
"""Deterministic post-extraction checks that decide if a receipt needs a human look."""

from __future__ import annotations

from app.currency import is_supported
from app.models import Receipt

MIN_CONFIDENCE = 0.7
SUM_TOLERANCE = 0.02  # 2% mismatch between line items (+tax) and total


def assess_receipt(r: Receipt) -> list[str]:
    if not r.readable:
        return ["Receipt is not readable"]

    reasons: list[str] = []
    if not r.vendor:
        reasons.append("Vendor name missing")
    if r.receipt_date is None:
        reasons.append("Date missing")
    if r.total is None:
        reasons.append("Total amount missing")

    present = {"vendor": r.vendor, "date": r.receipt_date, "total": r.total}
    for name, value in present.items():
        conf = getattr(r.confidence, name)
        if value is not None and conf < MIN_CONFIDENCE:
            reasons.append(f"Low confidence on {name} ({conf:.2f})")

    if not is_supported(r.currency):
        reasons.append(f"Unsupported currency {r.currency}")

    amounts = [i.amount for i in r.line_items if i.amount is not None]
    if r.total and amounts:
        # item prices may or may not already include tax; accept either reading
        with_tax = sum(amounts) + (r.tax or 0.0)
        candidates = (with_tax, sum(amounts))
        if all(abs(c - r.total) / r.total > SUM_TOLERANCE for c in candidates):
            reasons.append(f"Line items ({with_tax:.2f}) do not add up to total ({r.total:.2f})")

    return reasons
```

### FILE: backend/app/extraction.py  (137 lines)

```python
"""Vision-LLM receipt extraction via Pydantic AI (model-agnostic).

The model is chosen by `Settings.llm_model` (e.g. "anthropic:claude-sonnet-5-5",
"google:gemini-3.8-flash"). Results are cached by file hash + model so the demo
can run without network access.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import httpx2  # HTTP client used inside pydantic-ai; its transport errors escape the agent
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

from app.config import Settings, get_settings
from app.currency import to_inr
from app.ingest import LoadedFile, load_file
from app.models import ExtractedReceipt, Receipt
from app.quality import assess_receipt

INSTRUCTIONS = """\
You extract structured data from a photo or scan of an expense receipt.
- Read only what is printed. Never invent a value; use null when a field is absent.
- Dates on these receipts are day-first (DD/MM/YYYY). Output ISO YYYY-MM-DD.
- "Rs" or the rupee sign means INR. total is the final amount paid including tax.
- `category` is only a short free-text description of the kind of expense (for example
  "restaurant meal" or "petrol"); do not try to match any policy.
- Give honest per-field confidence: lower it for blur, glare, folds, or partial text.
- If the image is not a receipt or is unreadable, set readable=false.
"""

_RETRYABLE_STATUS = {429, 503}


def build_agent(model: Any) -> Agent[None, Receipt]:
    return Agent(
        model,
        output_type=Receipt,
        instructions=INSTRUCTIONS,
        retries=2,
        defer_model_check=True,  # don't require an API key until the first call
    )


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", model)


def _cache_path(settings: Settings, sha: str) -> Path:
    return settings.cache_dir / _slug(settings.llm_model) / f"{sha}.json"


def _read_cache(settings: Settings, sha: str) -> ExtractedReceipt | None:
    path = _cache_path(settings, sha)
    if not path.exists():
        return None
    return ExtractedReceipt.model_validate_json(path.read_text())


def _write_cache(settings: Settings, result: ExtractedReceipt) -> None:
    path = _cache_path(settings, result.file_sha256)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2))


def _user_content(loaded: LoadedFile) -> list[Any]:
    # The file name is deliberately not sent: it can leak the expected answer.
    prompt = "Extract the receipt in the attached image(s)."
    if loaded.embedded_text:
        prompt += f"\n\nText embedded in the PDF (may be incomplete):\n{loaded.embedded_text}"
    return [prompt, *(BinaryContent(p.data, media_type=p.media_type) for p in loaded.pages)]


async def _run_with_backoff(agent: Any, content: Any, attempts: int = 6, **run_kwargs: Any):
    """Retry transient failures (rate limit, overload, dropped connection) with backoff."""
    for n in range(attempts):
        try:
            return await agent.run(content, **run_kwargs)
        except (ModelHTTPError, httpx2.TransportError) as e:
            transient = isinstance(e, httpx2.TransportError) or (
                e.status_code in _RETRYABLE_STATUS and "PerDay" not in str(e.body)  # daily quota: waiting won't help
            )
            if not transient or n == attempts - 1:
                raise
            await asyncio.sleep(min(2 * 2**n, 30))  # 2, 4, 8, 16, 30s


def _finalise(loaded: LoadedFile, model: str, receipt: Receipt) -> ExtractedReceipt:
    reasons = assess_receipt(receipt)
    total_inr = to_inr(receipt.total, receipt.currency) if receipt.total is not None else None
    return ExtractedReceipt(
        source_file=loaded.name,
        file_sha256=loaded.sha256,
        model=model,
        receipt=receipt,
        total_inr=total_inr,
        needs_review=bool(reasons),
        review_reasons=reasons,
    )


async def extract_receipt(
    path: Path,
    *,
    agent: Any | None = None,
    settings: Settings | None = None,
) -> ExtractedReceipt:
    settings = settings or get_settings()
    loaded = load_file(path, max_side=settings.max_image_side, max_pdf_pages=settings.max_pdf_pages)

    if settings.use_extraction_cache:
        cached = _read_cache(settings, loaded.sha256)
        if cached is not None:
            return cached.model_copy(update={"source_file": loaded.name})

    agent = agent or build_agent(settings.llm_model)
    try:
        result = await _run_with_backoff(agent, _user_content(loaded))
    except UnexpectedModelBehavior as e:
        # The model kept returning output that failed validation.
        return ExtractedReceipt(
            source_file=loaded.name,
            file_sha256=loaded.sha256,
            model=settings.llm_model,
            review_reasons=["Automatic extraction failed; please enter details manually"],
            error=str(e),
        )

    extracted = _finalise(loaded, settings.llm_model, result.output)
    _write_cache(settings, extracted)
    if settings.llm_call_delay_s:
        await asyncio.sleep(settings.llm_call_delay_s)
    return extracted
```

### FILE: backend/app/duplicates.py  (83 lines)

```python
"""Duplicate receipt detection.

Two layers: identical file bytes, and "same receipt" by content (vendor, date, amount).
Image hashing is deliberately not used: on same-template receipts different bills
hash identically and re-photographed copies hash far apart (measured on the
synthetic set), so it produces both false positives and false negatives.
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass

VENDOR_SIMILARITY = 0.85
AMOUNT_TOLERANCE = 0.01


@dataclass(frozen=True)
class DupKey:
    file: str
    sha256: str
    vendor: str | None
    date: dt.date | None
    total: float | None
    currency: str
    receipt_number: str | None = None


@dataclass(frozen=True)
class DupMatch:
    original: str
    reason: str  # human-readable


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.casefold())


def _same_vendor(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio() >= VENDOR_SIMILARITY


def _same_receipt(a: DupKey, b: DupKey) -> bool:
    if None in (a.vendor, b.vendor, a.date, b.date, a.total, b.total):
        return False
    if a.date != b.date or a.currency != b.currency:
        return False
    if abs(a.total - b.total) > AMOUNT_TOLERANCE:
        return False
    if not _same_vendor(a.vendor, b.vendor):
        return False
    # Two different bill numbers mean two real purchases (e.g. two identical taxi fares).
    if a.receipt_number and b.receipt_number and _norm(a.receipt_number) != _norm(b.receipt_number):
        return False
    return True


def find_duplicates(keys: Sequence[DupKey], exempt: Collection[str] = ()) -> dict[str, DupMatch]:
    """Map duplicate file -> its original (the earliest earlier receipt).

    Files in `exempt` (the user said "not a duplicate") are never reported as duplicates
    but can still be the original that later receipts are compared against.
    """
    result: dict[str, DupMatch] = {}
    originals: list[DupKey] = []
    for key in keys:
        match: DupMatch | None = None
        if key.file not in exempt:
            for orig in originals:
                if orig.sha256 == key.sha256:
                    match = DupMatch(orig.file, "identical file")
                    break
                if _same_receipt(orig, key):
                    match = DupMatch(orig.file, "same vendor, date and amount")
                    break
        if match:
            result[key.file] = match
        else:
            originals.append(key)
    return result
```

### FILE: backend/app/grouping.py  (34 lines)

```python
"""Group dated expenses into trips / periods by date proximity."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass, field

GAP_DAYS = 3  # a gap longer than this starts a new group


@dataclass
class Group:
    id: str
    start: dt.date
    end: dt.date
    files: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        if self.start == self.end:
            return f"Expenses on {self.start:%d %b %Y}"
        return f"Expenses {self.start:%d %b} – {self.end:%d %b %Y}"


def group_by_date(items: Sequence[tuple[str, dt.date]], gap_days: int = GAP_DAYS) -> list[Group]:
    groups: list[Group] = []
    for file, date in sorted(items, key=lambda x: (x[1], x[0])):
        if groups and (date - groups[-1].end).days <= gap_days:
            groups[-1].end = date
            groups[-1].files.append(file)
        else:
            groups.append(Group(id=f"g-{date.isoformat()}", start=date, end=date, files=[file]))
    return groups
```

### FILE: backend/app/policy/__init__.py  *(empty file)*

```python
```

### FILE: backend/app/policy/schema.py  (129 lines)

```python
"""Structured policy constraints produced by the LLM interpreter and enforced by code.

The LLM reads policy prose and fills these models. Nothing here contains policy
values: limits, grades and categories all come from the documents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Unit = Literal["per_receipt", "per_night", "per_day", "per_month"]
OverLimitAction = Literal["partial", "needs_approval", "reject"]


class Employee(BaseModel):
    id: str
    name: str
    grade: str
    role: str
    base_city: str


def load_employee(path: Path) -> Employee:
    return Employee.model_validate_json(path.read_text())


class CategoryDef(BaseModel):
    id: str = Field(description="short lowercase snake_case id, e.g. 'meals' or 'lodging'")
    label: str = Field(description="human-readable name")
    description: str = Field(description="what kinds of expenses belong in this category, per the policy")


class _Cited(BaseModel):
    clause: str = Field(description="clause number exactly as printed in the document, e.g. '2.1'")
    quote: str = Field(description="the words from that clause that support this item, copied verbatim")
    document: str = Field("", description="leave empty; filled in by the system")


class Entitlement(_Cited):
    category: str = Field(description="id of a category defined in `categories`")
    grades: list[str] = Field(
        description="every grade code allowed to claim the category, with grade bands expanded "
        "to individual codes using the document's own definitions"
    )


class Limit(_Cited):
    category: str
    amount: float
    currency: str = Field("INR", description="ISO 4217 code")
    unit: Unit
    grades: list[str] | None = Field(
        None, description="grade codes this limit applies to, or null when it applies to all grades"
    )
    over_limit_action: OverLimitAction = Field(
        description="partial: the policy reimburses up to the limit; needs_approval: above the limit "
        "only with a manager exception; reject: above the limit is not reimbursed"
    )
    requires_approval: bool = Field(
        False, description="true if the policy requires prior approval even when under the limit"
    )


class Exclusion(_Cited):
    category: str
    reason: str


class AgeRule(_Cited):
    max_age_days: int = Field(description="maximum age of a receipt, in days")


class PolicyConstraints(BaseModel):
    categories: list[CategoryDef] = Field(default_factory=list)
    entitlements: list[Entitlement] = Field(default_factory=list)
    limits: list[Limit] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)
    age_rules: list[AgeRule] = Field(default_factory=list)


class PolicySet(PolicyConstraints):
    """All interpreted documents merged. `documents` maps file name -> content hash."""

    documents: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def merge(cls, parts: list[tuple[str, str, PolicyConstraints]]) -> PolicySet:
        out = cls()
        seen: set[str] = set()
        for name, sha, c in parts:
            out.documents[name] = sha
            for cat in c.categories:
                if cat.id not in seen:
                    seen.add(cat.id)
                    out.categories.append(cat)
            out.entitlements += c.entitlements
            out.limits += c.limits
            out.exclusions += c.exclusions
            out.age_rules += c.age_rules
        return out

    def category_ids(self) -> set[str]:
        return {c.id for c in self.categories}

    def label(self, category: str) -> str:
        return next((c.label for c in self.categories if c.id == category), category)

    def exclusion_for(self, category: str) -> Exclusion | None:
        return next((x for x in self.exclusions if x.category == category), None)

    def entitlements_for(self, category: str) -> list[Entitlement]:
        return [e for e in self.entitlements if e.category == category]

    def entitlement_for(self, category: str, grade: str) -> Entitlement | None:
        return next((e for e in self.entitlements_for(category) if grade in e.grades), None)

    def limit_for(self, category: str, grade: str) -> Limit | None:
        """Grade-specific limits win over general ones."""
        candidates = [x for x in self.limits if x.category == category and (x.grades is None or grade in x.grades)]
        candidates.sort(key=lambda x: x.grades is None)
        return candidates[0] if candidates else None

    def eligible_categories(self, grade: str) -> list[str]:
        excluded = {x.category for x in self.exclusions}
        ids = {e.category for e in self.entitlements if grade in e.grades}
        return sorted(ids - excluded)
```

### FILE: backend/app/policy/clauses.py  (124 lines)

```python
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
```

### FILE: backend/app/policy/interpreter.py  (167 lines)

```python
"""LLM policy interpreter: policy prose in, grounded structured constraints out.

The model proposes constraints; deterministic code verifies each one is backed by
a verbatim quote from the clause it cites, and that every number it reports is
in that quote. Failures are fed back to the model (Pydantic AI `ModelRetry`).
Results are cached by document hash, so editing a policy document is all it
takes for new limits to apply: the next evaluation re-interprets it.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior

from app.config import Settings, get_settings
from app.extraction import _run_with_backoff, _slug
from app.policy.clauses import load_documents, normalize, parse_clauses
from app.policy.schema import PolicyConstraints, PolicySet

INSTRUCTIONS = """\
You convert a corporate reimbursement policy document into structured constraints.
Rules:
- Use only what the document says. Never invent a limit, grade, or category.
- Every item must cite its clause number and a verbatim `quote` from that clause. A limit's
  amount must appear in its quote.
- Define a category for each kind of expense the document makes reimbursable or excludes. Use short
  lowercase snake_case ids. Reuse the ids you are given from other documents instead of creating
  near-duplicates.
- Expand grade bands (for example "Manager grades") into individual grade codes using the
  document's own definitions. If the document does not define the codes, leave grades empty.
- Choose `unit` from the wording: "per night", "per receipt", "per day", "per month".
- over_limit_action: "partial" if the document says the amount up to the limit is reimbursed;
  "needs_approval" if above the limit only with a manager exception; otherwise "reject".
- Put things the policy says are never reimbursable under `exclusions`, with a category for them.
- Do not output an item for clauses that contain no constraint.
"""


class PolicyInterpretationError(RuntimeError):
    pass


_NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in _NUM_RE.findall(text)]


def grounding_problems(c: PolicyConstraints, clauses: dict[str, str]) -> list[str]:
    """Return a list of human-readable problems; empty means every item is grounded."""
    problems: list[str] = []
    known = {x.id for x in c.categories}

    def check(kind: str, item: Any) -> str | None:
        text = clauses.get(item.clause)
        if text is None:
            problems.append(f"{kind}: clause '{item.clause}' does not exist in the document")
            return None
        if normalize(item.quote) not in normalize(text):
            problems.append(f"{kind} {item.clause}: quote is not copied verbatim from that clause")
            return None
        return normalize(item.quote)

    def check_category(kind: str, item: Any) -> None:
        if item.category not in known:
            problems.append(f"{kind} {item.clause}: category '{item.category}' is not in `categories`")

    for e in c.entitlements:
        check("entitlement", e)
        check_category("entitlement", e)
    for x in c.exclusions:
        check("exclusion", x)
        check_category("exclusion", x)
    for lim in c.limits:
        q = check("limit", lim)
        check_category("limit", lim)
        if q is not None and not any(abs(n - lim.amount) < 1e-6 for n in _numbers(q)):
            problems.append(f"limit {lim.clause}: amount {lim.amount:g} does not appear in the quote")
    for a in c.age_rules:
        q = check("age rule", a)
        if q is not None and not any(abs(n - a.max_age_days) < 1e-6 for n in _numbers(q)):
            problems.append(f"age rule {a.clause}: {a.max_age_days} does not appear in the quote")
    return problems


def build_interpreter_agent(model: Any) -> Agent[dict[str, str], PolicyConstraints]:
    agent: Agent[dict[str, str], PolicyConstraints] = Agent(
        model,
        output_type=PolicyConstraints,
        deps_type=dict,
        instructions=INSTRUCTIONS,
        retries=3,
        defer_model_check=True,
    )

    @agent.output_validator
    def _grounded(ctx: RunContext[dict[str, str]], out: PolicyConstraints) -> PolicyConstraints:
        problems = grounding_problems(out, ctx.deps)
        if problems:
            raise ModelRetry("Fix these problems and return the full result again:\n- " + "\n- ".join(problems))
        return out

    return agent


def _cache_path(settings: Settings, key: str) -> Path:
    return settings.policy_cache_dir / _slug(settings.llm_model) / f"{key}.json"


async def interpret_document(
    name: str,
    text: str,
    *,
    known_categories: list[str] | None = None,
    agent: Any | None = None,
    settings: Settings | None = None,
) -> tuple[str, PolicyConstraints]:
    """Returns (content hash, constraints)."""
    settings = settings or get_settings()
    known = sorted(known_categories or [])
    sha = hashlib.sha256(text.encode()).hexdigest()
    key = hashlib.sha256(f"{sha}|{','.join(known)}".encode()).hexdigest()[:32]
    path = _cache_path(settings, key)
    if path.exists():
        return sha, PolicyConstraints.model_validate_json(path.read_text())

    clauses = {c.number: c.text for c in parse_clauses(name, text)}
    agent = agent or build_interpreter_agent(settings.llm_model)
    prompt = f"Document file name: {name}\n"
    if known:
        prompt += f"Category ids already defined by other documents (reuse them): {', '.join(known)}\n"
    prompt += f"\n--- DOCUMENT ---\n{text}"
    try:
        result = await _run_with_backoff(agent, prompt, deps=clauses)
    except UnexpectedModelBehavior as e:
        raise PolicyInterpretationError(f"Could not interpret {name}: {e}") from e

    constraints = result.output
    for items in (constraints.entitlements, constraints.limits, constraints.exclusions, constraints.age_rules):
        for item in items:
            item.document = name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(constraints.model_dump_json(indent=2))
    return sha, constraints


async def load_policy_set(
    policy_dir: Path,
    *,
    agent: Any | None = None,
    settings: Settings | None = None,
) -> PolicySet:
    """Interpret every policy document in the directory (cached) and merge the results."""
    settings = settings or get_settings()
    parts = []
    known: list[str] = []
    for name, text in load_documents(policy_dir).items():
        sha, constraints = await interpret_document(name, text, known_categories=known, agent=agent, settings=settings)
        known = sorted({*known, *(c.id for c in constraints.categories)})
        parts.append((name, sha, constraints))
    return PolicySet.merge(parts)
```

### FILE: backend/app/policy/evaluator.py  (191 lines)

```python
"""Deterministic enforcement of interpreted policy constraints.

All money arithmetic happens here, never in the LLM. Every decision carries the
clause references and verbatim quotes it relied on, plus a plain-language
explanation built from the computed numbers.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field

from app.currency import to_inr
from app.policy.clauses import doc_code
from app.policy.schema import Employee, Limit, PolicySet, _Cited


class Outcome(StrEnum):
    APPROVED = "approved"
    PARTIAL = "partial"
    FLAGGED = "flagged"  # resolvable: needs a justification, approval or clarification
    REJECTED = "rejected"


class ClauseCite(BaseModel):
    ref: str
    document: str
    quote: str


class Decision(BaseModel):
    outcome: Outcome
    category: str
    claimed_inr: float
    eligible_inr: float
    explanation: str
    cites: list[ClauseCite] = Field(default_factory=list)
    needs: list[str] = Field(default_factory=list)


class UsageTracker:
    """Tracks how much of per-day / per-month limits earlier receipts have used."""

    def __init__(self) -> None:
        self.used: dict[tuple, float] = defaultdict(float)


def inr(x: float) -> str:
    return f"INR {x:,.0f}" if abs(x - round(x)) < 0.005 else f"INR {x:,.2f}"


def _cite(item: _Cited) -> ClauseCite:
    return ClauseCite(ref=f"{doc_code(item.document)}-{item.clause}", document=item.document, quote=item.quote)


def _quoted(c: ClauseCite) -> str:
    return f'Policy {c.ref}: "{c.quote}"'


def _bucket(limit: Limit, date: dt.date | None) -> tuple:
    if limit.unit == "per_day" and date:
        return (limit.document, limit.clause, date)
    if limit.unit == "per_month" and date:
        return (limit.document, limit.clause, date.year, date.month)
    return ()  # per receipt / per night: nothing shared across receipts


def evaluate_line(
    *,
    category: str,
    claimed_inr: float,
    date: dt.date | None,
    employee: Employee,
    policy: PolicySet,
    today: dt.date,
    tracker: UsageTracker,
    nights: int | None = None,
    justification: str | None = None,
) -> Decision:
    def decide(
        outcome: Outcome, eligible: float, text: str, cites: list[ClauseCite], needs: list[str] | None = None
    ) -> Decision:
        return Decision(
            outcome=outcome,
            category=category,
            claimed_inr=claimed_inr,
            eligible_inr=round(eligible, 2),
            explanation=text,
            cites=cites,
            needs=needs or [],
        )

    label = policy.label(category)

    if category not in policy.category_ids():
        return decide(
            Outcome.FLAGGED, 0.0, "No policy category matches this expense; please choose one.", [], ["category"]
        )

    if (x := policy.exclusion_for(category)) is not None:
        c = _cite(x)
        return decide(Outcome.REJECTED, 0.0, f"{label} is not reimbursable: {x.reason}. {_quoted(c)}", [c])

    if not any(policy.entitlements_for(category)):
        return decide(Outcome.REJECTED, 0.0, f"No policy clause makes {label} reimbursable.", [])
    ent = policy.entitlement_for(category, employee.grade)
    if ent is None:
        c = _cite(policy.entitlements_for(category)[0])
        return decide(
            Outcome.REJECTED, 0.0, f"Grade {employee.grade} is not eligible to claim {label}. {_quoted(c)}", [c]
        )
    cites = [_cite(ent)]

    for rule in policy.age_rules:
        if date and (today - date).days > rule.max_age_days:
            c = _cite(rule)
            return decide(
                Outcome.REJECTED,
                0.0,
                f"The receipt is {(today - date).days} days old; the limit is {rule.max_age_days} days. {_quoted(c)}",
                [c],
            )

    limit = policy.limit_for(category, employee.grade)
    if limit is None:
        return decide(
            Outcome.APPROVED, claimed_inr, f"{label} is reimbursable with no amount limit. {_quoted(cites[0])}", cites
        )

    lc = _cite(limit)
    cites.append(lc)
    cap = to_inr(limit.amount, limit.currency) or limit.amount
    if limit.unit == "per_night":
        n = max(nights or 1, 1)
        cap, scope = cap * n, f"{inr(cap)} per night x {n}"
    else:
        scope = f"{inr(cap)} {limit.unit.replace('_', ' ')}"
    bucket = _bucket(limit, date)
    remaining = max(cap - tracker.used[bucket], 0.0) if bucket else cap

    if claimed_inr <= remaining + 0.005:
        if limit.requires_approval and not justification:
            return decide(
                Outcome.FLAGGED,
                0.0,
                f"{label} needs prior approval before it can be reimbursed. {_quoted(lc)}",
                cites,
                ["approval reference or justification"],
            )
        tracker.used[bucket] += claimed_inr
        return decide(Outcome.APPROVED, claimed_inr, f"Within the {scope} limit. {_quoted(lc)}", cites)

    over = claimed_inr - remaining
    if limit.over_limit_action == "partial":
        tracker.used[bucket] += remaining
        if remaining <= 0:
            return decide(Outcome.REJECTED, 0.0, f"The {scope} limit is already used up. {_quoted(lc)}", cites)
        return decide(
            Outcome.PARTIAL,
            remaining,
            f"The bill is {inr(claimed_inr)} but the limit is {scope}. Reimbursing {inr(remaining)}; "
            f"the excess {inr(over)} is not reimbursable. {_quoted(lc)}",
            cites,
        )
    if limit.over_limit_action == "needs_approval":
        if justification:
            tracker.used[bucket] += claimed_inr
            return decide(
                Outcome.APPROVED,
                claimed_inr,
                f"The bill is {inr(claimed_inr)}, above the {scope} limit; approved as an exception on "
                f"the recorded justification. {_quoted(lc)}",
                cites,
            )
        return decide(
            Outcome.FLAGGED,
            0.0,
            f"The bill is {inr(claimed_inr)}, above the {scope} limit. It can be reimbursed only as an "
            f"approved exception. {_quoted(lc)}",
            cites,
            ["manager-approved justification"],
        )
    return decide(
        Outcome.REJECTED,
        0.0,
        f"The bill is {inr(claimed_inr)}, above the {scope} limit, and the excess is not reimbursable. {_quoted(lc)}",
        cites,
    )
```

### FILE: backend/app/classifier.py  (135 lines)

```python
"""AI expense classification into the employee's policy categories, with reasoning.

Text-only LLM call: it sees what was extracted from the bill plus the categories the
policy defines (and which of them this employee may claim). The category list comes
from the interpreted policy, so adding a category to a policy document needs no code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior

from app.config import Settings, get_settings
from app.extraction import _run_with_backoff, _slug
from app.models import ExtractedReceipt
from app.policy.schema import Employee, PolicySet

UNKNOWN = "unknown"

INSTRUCTIONS = """\
You classify one expense into a reimbursement category defined by the company's policy.
- Choose from the listed category ids only. Judge by what was actually bought (line items,
  vendor type), not by how the employee might want to claim it.
- Prefer a category the employee is eligible for when it genuinely fits; if the expense only fits a
  category that is excluded or unavailable to their grade, still choose that category so the
  policy can explain the outcome.
- Give a one or two sentence `reasoning` an employee can read.
- Set needs_clarification=true ONLY when the choice between categories would change what is
  reimbursed (different eligibility or limits) and the bill itself does not settle it, or when you
  cannot tell what was bought. Then pick the most likely category and ask one short question.
- Never ask about things collected elsewhere: the business purpose, the date, the amount, or taxes
  (a total above the sum of line items is normal tax), and never ask just to confirm an obvious category.
"""


class Classification(BaseModel):
    category: str = Field(description="id of one listed policy category")
    reasoning: str = Field(description="why this category fits this expense")
    confidence: float = Field(ge=0, le=1)
    needs_clarification: bool = False
    clarification_question: str | None = None


def unknown_classification(reason: str) -> Classification:
    return Classification(
        category=UNKNOWN,
        reasoning=reason,
        confidence=0.0,
        needs_clarification=True,
        clarification_question="What was this expense for?",
    )


def build_classifier_agent(model: Any) -> Agent[set[str], Classification]:
    agent: Agent[set[str], Classification] = Agent(
        model,
        output_type=Classification,
        deps_type=set,
        instructions=INSTRUCTIONS,
        retries=2,
        defer_model_check=True,
    )

    @agent.output_validator
    def _known(ctx: RunContext[set[str]], out: Classification) -> Classification:
        if out.category not in ctx.deps:
            raise ModelRetry(f"category must be one of: {', '.join(sorted(ctx.deps))}")
        return out

    return agent


def describe_categories(policy: PolicySet, employee: Employee) -> str:
    eligible = set(policy.eligible_categories(employee.grade))
    lines = []
    for c in policy.categories:
        if policy.exclusion_for(c.id):
            status = "never reimbursable"
        elif c.id in eligible:
            status = f"available to grade {employee.grade}"
        else:
            status = f"NOT available to grade {employee.grade}"
        lines.append(f"- {c.id}: {c.label}. {c.description} [{status}]")
    return "\n".join(lines)


def _prompt(e: ExtractedReceipt, employee: Employee, policy: PolicySet) -> str:
    r = e.receipt
    assert r is not None
    items = "; ".join(f"{i.description} ({i.amount})" for i in r.line_items) or "none listed"
    return (
        f"Employee: grade {employee.grade}, role {employee.role}, base city {employee.base_city}\n\n"
        f"Policy categories:\n{describe_categories(policy, employee)}\n\n"
        f"Expense:\n- vendor: {r.vendor}\n- date: {r.receipt_date}\n- total: {r.total} {r.currency}\n"
        f"- line items: {items}\n- extractor's description: {r.category}\n"
        f"- nights: {r.nights}\n- notes: {r.notes}\n"
    )


def _cache_path(settings: Settings, e: ExtractedReceipt, employee: Employee, policy: PolicySet) -> Path:
    key = hashlib.sha256(
        f"{e.file_sha256}|{sorted(policy.documents.items())}|{employee.grade}|{settings.llm_model}|{INSTRUCTIONS}".encode()
    ).hexdigest()[:32]
    return settings.classification_cache_dir / _slug(settings.llm_model) / f"{key}.json"


async def classify_receipt(
    e: ExtractedReceipt,
    employee: Employee,
    policy: PolicySet,
    *,
    agent: Any | None = None,
    settings: Settings | None = None,
) -> Classification:
    settings = settings or get_settings()
    if e.receipt is None or not e.receipt.readable:
        return unknown_classification("The bill could not be read.")

    path = _cache_path(settings, e, employee, policy)
    if path.exists():
        return Classification.model_validate_json(path.read_text())

    agent = agent or build_classifier_agent(settings.llm_model)
    try:
        result = await _run_with_backoff(agent, _prompt(e, employee, policy), deps=policy.category_ids())
    except UnexpectedModelBehavior:
        return unknown_classification("Automatic classification failed.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.output.model_dump_json(indent=2))
    return result.output
```

### FILE: backend/app/claim.py  (374 lines)

```python
"""Turn extracted + classified receipts into a claim: what is complete, missing or questionable.

AI decides what each expense is (classifier) and what the policy allows (interpreter);
this module is the deterministic glue: dedupe, enforce the interpreted constraints with
exact arithmetic, group, and work out the minimal questions needed to reach READY.
Every item carries the policy clauses and plain-language reasons behind its status.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field

from app.classifier import UNKNOWN, Classification, unknown_classification
from app.currency import to_inr
from app.duplicates import DupKey, find_duplicates
from app.grouping import Group, group_by_date
from app.models import ExtractedReceipt
from app.policy.evaluator import Decision, Outcome, UsageTracker, evaluate_line
from app.policy.schema import Employee, PolicySet

_SOFT_REASON_PREFIXES = ("Low confidence", "Line items")
CLARIFY_BELOW_CONFIDENCE = 0.75


class ItemStatus(StrEnum):
    COMPLETE = "complete"
    MISSING_INFO = "missing_info"
    QUESTIONABLE = "questionable"
    DUPLICATE = "duplicate"
    INELIGIBLE = "ineligible"


class ClaimState(StrEnum):
    READY = "ready"
    NEEDS_INPUT = "needs_input"
    BLOCKED = "blocked"


class ItemInput(BaseModel):
    """What the employee told us about one receipt (answers and corrections)."""

    vendor: str | None = None
    receipt_date: dt.date | None = None
    total: float | None = None
    currency: str | None = None
    category: str | None = None  # employee overrides the AI's category
    business_purpose: str | None = None
    justification: str | None = None
    confirmed: bool = False  # "the extracted details are right"
    not_duplicate: bool = False

    def has_corrections(self) -> bool:
        return any(v is not None for v in (self.vendor, self.receipt_date, self.total, self.currency))


class ClaimInputs(BaseModel):
    items: dict[str, ItemInput] = Field(default_factory=dict)  # keyed by source file
    group_purposes: dict[str, str] = Field(default_factory=dict)  # keyed by group id


class ClaimItem(BaseModel):
    file: str
    vendor: str | None
    receipt_date: dt.date | None
    total: float | None
    currency: str
    total_inr: float | None
    category: str
    category_source: str = "ai"  # ai | employee
    category_reasoning: str = ""
    status: ItemStatus
    reasons: list[str] = Field(default_factory=list)
    decision: Decision | None = None
    eligible_inr: float = 0.0
    duplicate_of: str | None = None
    group_id: str | None = None


class ClaimGroup(BaseModel):
    id: str
    title: str
    start: dt.date
    end: dt.date
    files: list[str]
    eligible_inr: float


class Question(BaseModel):
    id: str
    kind: str  # field | clarify | purpose | justify | confirm
    target: str  # file name or group id
    text: str
    fields: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    state: ClaimState
    employee: Employee
    items: list[ClaimItem]
    groups: list[ClaimGroup]
    questions: list[Question]
    eligible_by_category: dict[str, float]
    claimed_inr: float  # what the bills add up to (included items)
    eligible_inr: float  # what policy allows to be reimbursed
    counts: dict[str, int]


@dataclass
class _Eff:
    """An extracted receipt with the employee's corrections applied."""

    e: ExtractedReceipt
    inp: ItemInput
    vendor: str | None
    date: dt.date | None
    total: float | None
    currency: str
    total_inr: float | None

    @property
    def file(self) -> str:
        return self.e.source_file

    @property
    def label(self) -> str:
        return self.vendor or self.file


def _effective(e: ExtractedReceipt, inp: ItemInput) -> _Eff:
    r = e.receipt
    total = inp.total if inp.total is not None else (r.total if r else None)
    currency = (inp.currency or (r.currency if r else "INR")).upper()
    return _Eff(
        e,
        inp,
        inp.vendor or (r.vendor if r else None),
        inp.receipt_date or (r.receipt_date if r else None),
        total,
        currency,
        to_inr(total, currency) if total is not None else None,
    )


def _dup_key(x: _Eff) -> DupKey:
    receipt_number = x.e.receipt.receipt_number if x.e.receipt else None
    return DupKey(x.file, x.e.file_sha256, x.vendor, x.date, x.total, x.currency, receipt_number)


def _new_item(x: _Eff, cls: Classification, **extra) -> ClaimItem:
    """A claim item for one receipt; the employee's category choice wins over the AI's."""
    chosen = bool(x.inp.category)
    return ClaimItem(
        file=x.file,
        vendor=x.vendor,
        receipt_date=x.date,
        total=x.total,
        currency=x.currency,
        total_inr=x.total_inr,
        category=x.inp.category or cls.category,
        category_source="employee" if chosen else "ai",
        category_reasoning="Chosen by the employee." if chosen else cls.reasoning,
        **extra,
    )


def _triage(
    effs: list[_Eff],
    classifications: Mapping[str, Classification],
    employee: Employee,
    policy: PolicySet,
    today: dt.date,
) -> tuple[dict[str, ClaimItem], dict[str, Classification], list[_Eff]]:
    """Stage 1: mark duplicates, evaluate the policy for the rest, and set aside what policy rejects.

    Returns every item by file name, the classification used for each file, and the receipts that stay in play.
    """
    dups = find_duplicates([_dup_key(x) for x in effs], exempt={x.file for x in effs if x.inp.not_duplicate})
    items: dict[str, ClaimItem] = {}
    cls_of: dict[str, Classification] = {}
    active: list[_Eff] = []
    tracker = UsageTracker()  # shared so per-day and per-month limits span receipts, in input order
    for x in effs:
        cls = classifications.get(x.file) or unknown_classification("Not classified.")
        cls_of[x.file] = cls
        if x.file in dups:
            d = dups[x.file]
            reason = f"Duplicate of {d.original} ({d.reason}); left out of the claim"
            items[x.file] = _new_item(x, cls, status=ItemStatus.DUPLICATE, duplicate_of=d.original, reasons=[reason])
            continue
        decision = evaluate_line(
            category=x.inp.category or cls.category,
            claimed_inr=x.total_inr or 0.0,
            date=x.date,
            employee=employee,
            policy=policy,
            today=today,
            tracker=tracker,
            nights=x.e.receipt.nights if x.e.receipt else None,
            justification=x.inp.justification,
        )
        if decision.outcome is Outcome.REJECTED:
            items[x.file] = _new_item(
                x, cls, status=ItemStatus.INELIGIBLE, decision=decision, reasons=[decision.explanation]
            )
            continue
        items[x.file] = _new_item(x, cls, status=ItemStatus.COMPLETE, decision=decision)
        active.append(x)
    return items, cls_of, active


def _missing_basics(x: _Eff) -> list[str]:
    missing = [name for name, value in (("vendor", x.vendor), ("date", x.date), ("amount", x.total)) if value is None]
    if x.total is not None and x.total_inr is None:
        missing.append("currency")  # unsupported currency: ask for an INR amount
    return missing


def _category_unclear(x: _Eff, cls: Classification, item: ClaimItem, policy: PolicySet) -> bool:
    """Only interrupt the employee when the model both asks and is genuinely unsure (or the category is unusable)."""
    if x.inp.category:
        return False
    unsure = cls.needs_clarification and cls.confidence < CLARIFY_BELOW_CONFIDENCE
    return unsure or item.category == UNKNOWN or item.category not in policy.category_ids()


def _assess_item(
    x: _Eff, item: ClaimItem, cls: Classification, policy: PolicySet, eligible_cats: list[str], inputs: ClaimInputs
) -> tuple[list[Question], bool]:
    """Stage 2: decide one item's status and the questions it needs.

    Returns (questions, needs_business_purpose). Basics are asked first; nothing else is asked for that receipt.
    """
    decision = item.decision
    assert decision is not None
    questions: list[Question] = []

    missing = _missing_basics(x)
    if missing:
        item.status = ItemStatus.MISSING_INFO
        item.reasons.append(f"Missing {', '.join(missing)}")
        text = f"{x.label}: please provide the {' and '.join(missing)}."
        questions.append(Question(id=f"field:{x.file}", kind="field", target=x.file, fields=missing, text=text))
        return questions, False

    status = ItemStatus.COMPLETE
    if _category_unclear(x, cls, item, policy):
        status = ItemStatus.QUESTIONABLE
        ask = cls.clarification_question or "Which category does this expense belong to?"
        item.reasons.append("Category unclear")
        questions.append(
            Question(
                id=f"clarify:{x.file}", kind="clarify", target=x.file, options=eligible_cats, text=f"{x.label}: {ask}"
            )
        )
    elif decision.outcome is Outcome.FLAGGED:
        status = ItemStatus.QUESTIONABLE
        item.reasons.append(decision.explanation)
        needed = " and ".join(decision.needs) or "a justification"
        text = f"{x.label}: {decision.explanation} Please provide {needed}."
        questions.append(Question(id=f"justify:{x.file}", kind="justify", target=x.file, text=text))
    elif decision.outcome is Outcome.PARTIAL:
        item.reasons.append(decision.explanation)

    soft = [r for r in x.e.review_reasons if r.startswith(_SOFT_REASON_PREFIXES)]
    if soft and not (x.inp.confirmed or x.inp.has_corrections()):
        status = ItemStatus.QUESTIONABLE
        item.reasons.extend(soft)
        text = f"{x.label}: {'; '.join(soft)}. Are the extracted details correct?"
        questions.append(Question(id=f"confirm:{x.file}", kind="confirm", target=x.file, text=text))

    needs_purpose = not (x.inp.business_purpose or inputs.group_purposes.get(item.group_id or ""))
    if needs_purpose:
        if status is ItemStatus.COMPLETE:
            status = ItemStatus.MISSING_INFO
        item.reasons.append("Business purpose needed")
    item.status = status
    item.eligible_inr = decision.eligible_inr if decision.outcome is not Outcome.FLAGGED else 0.0
    return questions, needs_purpose


def _purpose_questions(missing: dict[str, list[str]], groups: dict[str, Group]) -> list[Question]:
    """One business-purpose question per trip group, not per receipt."""
    return [
        Question(
            id=f"purpose:{gid}",
            kind="purpose",
            target=gid,
            text=f"What was the business purpose of these {len(files)} receipt(s)? ({groups[gid].title})",
        )
        for gid, files in missing.items()
    ]


def _assemble(
    effs: list[_Eff], items: dict[str, ClaimItem], groups: list[Group], questions: list[Question], employee: Employee
) -> Claim:
    """Stage 3: claim state and totals over the items that are still included."""
    included = [i for i in items.values() if i.status not in (ItemStatus.DUPLICATE, ItemStatus.INELIGIBLE)]
    if not included:
        state = ClaimState.BLOCKED
    elif all(i.status is ItemStatus.COMPLETE for i in included):
        state = ClaimState.READY
    else:
        state = ClaimState.NEEDS_INPUT

    by_cat: dict[str, float] = defaultdict(float)
    for i in included:
        by_cat[i.category] += i.eligible_inr
    counts: dict[str, int] = defaultdict(int)
    for i in items.values():
        counts[i.status.value] += 1

    return Claim(
        state=state,
        employee=employee,
        items=[items[x.file] for x in effs],
        groups=[
            ClaimGroup(
                id=g.id,
                title=g.title,
                start=g.start,
                end=g.end,
                files=g.files,
                eligible_inr=round(sum(items[f].eligible_inr for f in g.files), 2),
            )
            for g in groups
        ],
        questions=questions,
        eligible_by_category={k: round(v, 2) for k, v in by_cat.items()},
        claimed_inr=round(sum(i.total_inr or 0 for i in included), 2),
        eligible_inr=round(sum(by_cat.values()), 2),
        counts=dict(counts),
    )


def build_claim(
    extracted: Sequence[ExtractedReceipt],
    classifications: Mapping[str, Classification],
    employee: Employee,
    policy: PolicySet,
    inputs: ClaimInputs | None = None,
    *,
    today: dt.date | None = None,
) -> Claim:
    """Turn extracted and classified receipts into a claim: statuses, minimal questions, totals and state."""
    inputs = inputs or ClaimInputs()
    today = today or dt.date.today()
    effs = [_effective(e, inputs.items.get(e.source_file, ItemInput())) for e in extracted]

    items, cls_of, active = _triage(effs, classifications, employee, policy, today)

    groups = group_by_date([(x.file, x.date) for x in active if x.date is not None])
    group_of = {f: g.id for g in groups for f in g.files}
    eligible_cats = policy.eligible_categories(employee.grade)

    questions: list[Question] = []
    purpose_missing: dict[str, list[str]] = defaultdict(list)
    for x in active:
        item = items[x.file]
        item.group_id = group_of.get(x.file)
        item_questions, needs_purpose = _assess_item(x, item, cls_of[x.file], policy, eligible_cats, inputs)
        questions.extend(item_questions)
        if needs_purpose and item.group_id:
            purpose_missing[item.group_id].append(x.file)
    questions.extend(_purpose_questions(purpose_missing, {g.id: g for g in groups}))

    return _assemble(effs, items, groups, questions, employee)
```

### FILE: backend/app/pipeline.py  (59 lines)

```python
"""Receipt files in -> extracted + classified receipts out (the AI half of the pipeline)."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx2
from pydantic_ai.exceptions import ModelAPIError

from app.classifier import Classification, build_classifier_agent, classify_receipt, unknown_classification
from app.config import Settings, get_settings
from app.extraction import build_agent, extract_receipt
from app.ingest import UnsupportedFileError
from app.models import ExtractedReceipt
from app.policy.schema import Employee, PolicySet


def _failed(path: Path, settings: Settings, message: str) -> ExtractedReceipt:
    return ExtractedReceipt(
        source_file=path.name,
        file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        model=settings.llm_model,
        review_reasons=[f"Could not process this file: {message}"],
        error=message,
    )


async def process_files(
    paths: Sequence[Path],
    employee: Employee,
    policy: PolicySet,
    *,
    settings: Settings | None = None,
    concurrency: int = 4,
    on_progress: Callable[[], None] | None = None,
) -> tuple[list[ExtractedReceipt], dict[str, Classification]]:
    """Extract and classify every file. One bad file never sinks the batch."""
    settings = settings or get_settings()
    extract_agent = build_agent(settings.llm_model)
    classify_agent = build_classifier_agent(settings.llm_model)
    gate = asyncio.Semaphore(concurrency)

    async def one(path: Path) -> tuple[ExtractedReceipt, Classification]:
        async with gate:
            try:
                e = await extract_receipt(path, agent=extract_agent, settings=settings)
                c = await classify_receipt(e, employee, policy, agent=classify_agent, settings=settings)
            except (UnsupportedFileError, ModelAPIError, httpx2.TransportError) as err:
                return _failed(path, settings, str(err)[:200]), unknown_classification("Not processed.")
            finally:
                if on_progress:
                    on_progress()
            return e, c

    results = await asyncio.gather(*(one(p) for p in paths))
    return [e for e, _ in results], {e.source_file: c for e, c in results}
```

### FILE: backend/app/finance.py  (81 lines)

```python
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
```

### FILE: backend/app/state.py  (200 lines)

```python
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
```

### FILE: backend/app/chat.py  (170 lines)

```python
"""Conversational assistant (agentic): answers questions about the claim and takes the employee's answers.

The agent never computes money or decides policy itself. It reads decisions the deterministic
engine already made (claim_status, explain_item), retrieves clauses from the policy documents
(search_policy, RAG), and records the employee's answers (record_answer), after which the claim
is rebuilt by code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic_ai import Agent, RunContext

from app.claim import Claim, ClaimItem
from app.extraction import _run_with_backoff
from app.policy.clauses import ClauseIndex, load_documents, parse_clauses
from app.state import AppState, Session

INSTRUCTIONS = """\
You are an expense reimbursement assistant helping an employee turn their receipts into a claim.
- Facts come from tools. Never guess amounts, statuses or policy. Call claim_status, explain_item or
  search_policy before answering questions about them.
- When the employee gives information that answers an open question or corrects a receipt, record it
  with record_answer, then say what changed and what (if anything) is still needed.
- When you explain a decision, mention the policy clause reference (like TEP-2.1) and the amounts
  from the tool output. Say plainly what is eligible and what is not.
- Ask for only what is missing. Do not submit the claim; the employee presses Submit when it is ready.
- Be brief: at most five short sentences. Plain text only: no markdown, no asterisks, no headings,
  no bullet lists. Mention only the receipts the question is about.
"""


@dataclass
class ChatDeps:
    app: AppState
    session: Session


def _inr(x: float | None) -> str:
    return "n/a" if x is None else f"INR {x:,.2f}"


def summarise(claim: Claim) -> str:
    lines = [
        f"Claim state: {claim.state.value}. Claimed {_inr(claim.claimed_inr)}, eligible {_inr(claim.eligible_inr)}.",
        "Counts: " + ", ".join(f"{k}={v}" for k, v in claim.counts.items()),
    ]
    if claim.questions:
        lines.append("Open questions:")
        lines += [f"- [{q.kind}] target={q.target}: {q.text}" for q in claim.questions]
    else:
        lines.append("No open questions.")
    lines.append("Groups: " + "; ".join(f"{g.id} ({g.title})" for g in claim.groups))
    return "\n".join(lines)


def _resolve(session: Session, text: str) -> tuple[str | None, str]:
    """Match a receipt by file name or vendor. Returns (file, error message)."""
    q = text.strip().casefold()
    names = [e.source_file for e in session.extracted]
    hits = [n for n in names if n.casefold() == q] or [n for n in names if q and q in n.casefold()]
    if not hits and session.claim:
        hits = [i.file for i in session.claim.items if i.vendor and q and q in i.vendor.casefold()]
    if len(hits) == 1:
        return hits[0], ""
    if not hits:
        return None, f"No receipt matches '{text}'. Receipts: {', '.join(names)}"
    return None, f"'{text}' matches several receipts: {', '.join(hits)}. Which one?"


def describe_item(i: ClaimItem) -> str:
    out = [
        f"{i.file}: {i.vendor or 'unknown vendor'} on {i.receipt_date or 'unknown date'}, "
        f"{_inr(i.total_inr)} claimed, {_inr(i.eligible_inr)} eligible. Status: {i.status.value}.",
        f"Category: {i.category} (chosen by {i.category_source}). Why: {i.category_reasoning}",
    ]
    if i.decision:
        out.append(f"Decision: {i.decision.outcome.value}. {i.decision.explanation}")
        for c in i.decision.cites:
            out.append(f'Clause {c.ref} ({c.document}): "{c.quote}"')
        if i.decision.needs:
            out.append("Needs: " + ", ".join(i.decision.needs))
    out += [f"Note: {r}" for r in i.reasons if not i.decision or r != i.decision.explanation]
    return "\n".join(out)


def build_chat_agent(model: Any) -> Agent[ChatDeps, str]:
    agent: Agent[ChatDeps, str] = Agent(
        model, deps_type=ChatDeps, instructions=INSTRUCTIONS, retries=2, defer_model_check=True
    )

    @agent.instructions
    def _context(ctx: RunContext[ChatDeps]) -> str:
        e = ctx.deps.app.employee
        return f"The employee is {e.name}, grade {e.grade}, {e.role}, based in {e.base_city}."

    @agent.tool
    async def claim_status(ctx: RunContext[ChatDeps]) -> str:
        """Current claim state, totals, counts and the open questions."""
        c = ctx.deps.session.claim
        return summarise(c) if c else "No receipts have been processed yet."

    @agent.tool
    async def explain_item(ctx: RunContext[ChatDeps], receipt: str) -> str:
        """Explain one receipt's category, policy decision, clauses and eligible amount.
        `receipt` is a file name or vendor name (partial is fine)."""
        s = ctx.deps.session
        file, err = _resolve(s, receipt)
        if file is None or s.claim is None:
            return err or "No claim yet."
        return describe_item(next(i for i in s.claim.items if i.file == file))

    @agent.tool
    async def search_policy(ctx: RunContext[ChatDeps], query: str) -> str:
        """Search the policy documents and return the most relevant clauses with their references."""
        docs = load_documents(ctx.deps.app.policy_dir)
        index = ClauseIndex([c for name, text in docs.items() for c in parse_clauses(name, text)])
        hits = index.search(query, k=3)
        if not hits:
            return "No relevant policy clause found."
        return "\n".join(f"{c.ref} ({c.document}, {c.heading}): {c.text}" for c, _ in hits)

    @agent.tool
    async def record_answer(
        ctx: RunContext[ChatDeps],
        kind: Literal[
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
        ],
        target: str,
        value: str = "",
    ) -> str:
        """Record the employee's answer or correction, then return the updated claim summary.
        purpose_group: target is a group id (e.g. g-2026-09-14), value is the business purpose.
        purpose_item / justification / category / vendor / date (YYYY-MM-DD) / amount / currency:
        target is a receipt file or vendor name. confirm / not_duplicate: target is a receipt."""
        s, app = ctx.deps.session, ctx.deps.app
        if kind != "purpose_group":
            file, err = _resolve(s, target)
            if file is None:
                return err
            target = file
        try:
            app.apply_answer(s, kind, target, value)
        except ValueError as e:
            return f"Could not record that: {e}"
        return "Recorded.\n" + summarise(s.claim) if s.claim else "Recorded."

    return agent


async def run_chat(app: AppState, session: Session, message: str) -> str:
    if app.chat_agent is None:
        app.chat_agent = build_chat_agent(app.settings.llm_model)
    await app.policy()  # make sure categories are loaded for validation
    result = await _run_with_backoff(
        app.chat_agent, message, deps=ChatDeps(app, session), message_history=session.chat_history
    )
    session.chat_history = result.all_messages()
    return result.output
```

### FILE: backend/app/main.py  (223 lines)

```python
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
```

