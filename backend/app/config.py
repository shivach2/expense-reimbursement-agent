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
