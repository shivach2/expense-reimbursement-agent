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
