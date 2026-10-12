"""Run extraction over receipts and score against synthetic ground truth.

python tools/extract_receipts.py                      # all synthetic receipts
python tools/extract_receipts.py --limit 3            # first 3 only
python tools/extract_receipts.py --model google:gemini-3.8-flash
python tools/extract_receipts.py path/to/receipt.png  # specific files (no scoring)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx2  # noqa: E402
from pydantic_ai.exceptions import ModelAPIError, UserError  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.extraction import build_agent, extract_receipt  # noqa: E402

RECEIPTS = ROOT / "data" / "synthetic" / "receipts"
TRUTH = ROOT / "data" / "synthetic" / "ground_truth.json"
FIELDS = ("vendor", "date", "total", "currency", "category")


def score(extracted, truth: dict) -> dict[str, bool]:
    r = extracted.receipt
    if r is None:
        return {f: False for f in FIELDS}
    return {
        "vendor": (r.vendor or "").casefold() == truth["vendor"].casefold(),
        "date": (r.receipt_date.isoformat() if r.receipt_date else None) == truth["date"],
        "total": r.total is not None and abs(r.total - truth["total"]) < 0.01,
        "currency": r.currency == truth["currency"],
        "category": r.category.value == truth["category"],
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--model")
    args = ap.parse_args()

    settings = get_settings()
    if args.model:
        settings = replace(settings, llm_model=args.model)

    files = args.files or sorted(RECEIPTS.iterdir())
    if args.limit:
        files = files[: args.limit]
    truth = {t["file"]: t for t in json.loads(TRUTH.read_text())} if TRUTH.exists() else {}

    agent = build_agent(settings.llm_model)  # one agent reused for all files
    totals = {f: [0, 0] for f in FIELDS}
    print(f"model: {settings.llm_model}\n")
    for path in files:
        try:
            res = await extract_receipt(path, agent=agent, settings=settings)
        except (ModelAPIError, httpx2.TransportError) as e:
            print(f"{path.name:<28} [FAILED] {type(e).__name__}: {str(e)[:120]}")
            if path.name in truth and not args.files:
                for f in totals:  # a failed call counts against accuracy
                    totals[f][1] += 1
            continue
        flag = "REVIEW" if res.needs_review else "ok"
        r = res.receipt
        summary = f"{r.vendor} | {r.receipt_date} | {r.total} {r.currency} | {r.category}" if r else res.error
        print(f"{path.name:<28} [{flag}] {summary}")
        for reason in res.review_reasons:
            print(f"{'':<28}   - {reason}")
        if path.name in truth and not args.files:
            for f, ok in score(res, truth[path.name]).items():
                totals[f][0] += ok
                totals[f][1] += 1

    if any(t[1] for t in totals.values()):
        print("\nfield accuracy vs ground truth")
        for f, (ok, n) in totals.items():
            print(f"  {f:<9} {ok}/{n}  ({ok / n:.0%})")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except UserError as e:  # e.g. missing API key
        sys.exit(f"Configuration error: {e}")
