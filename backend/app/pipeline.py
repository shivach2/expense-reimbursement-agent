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
