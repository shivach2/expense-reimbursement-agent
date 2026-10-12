"""Run the whole pipeline on the synthetic receipts and score it against ground truth.

    python tools/run_pipeline.py                      # all receipts, model from .env
    python tools/run_pipeline.py --model google:gemini-3.8-flash
    python tools/run_pipeline.py --policy-dir /tmp/changed_policies   # policy-change demo
Writes metrics to data/eval/<model>.json.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic_ai.exceptions import UserError  # noqa: E402

from app.claim import ItemStatus, build_claim  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.extraction import _slug  # noqa: E402
from app.pipeline import process_files  # noqa: E402
from app.policy.interpreter import load_policy_set  # noqa: E402
from app.policy.schema import load_employee  # noqa: E402

RECEIPTS = ROOT / "data" / "synthetic" / "receipts"
TRUTH = ROOT / "data" / "synthetic" / "ground_truth.json"
EXPECTED_INELIGIBLE = {"r12_old_receipt.png", "r24_pharmacy.png"}


def pct(ok: int, n: int) -> str:
    return f"{ok}/{n} ({ok / n:.0%})" if n else "n/a"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--policy-dir", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    args = ap.parse_args()

    settings = get_settings()
    if args.model:
        settings = replace(settings, llm_model=args.model)
    employee = load_employee(settings.employee_path)
    truth = {t["file"]: t for t in json.loads(TRUTH.read_text())}

    print(f"model: {settings.llm_model}   employee: {employee.name}, grade {employee.grade}")
    policy = await load_policy_set(args.policy_dir or settings.policy_dir, settings=settings)
    print(
        f"policy: {len(policy.documents)} documents -> {len(policy.limits)} limits, "
        f"{len(policy.entitlements)} entitlements, {len(policy.categories)} categories\n"
    )

    paths = sorted(RECEIPTS.iterdir())[: args.limit]
    extracted, cls = await process_files(paths, employee, policy, settings=settings)
    claim = build_claim(extracted, cls, employee, policy, today=args.today)

    print(f"{'file':<26}{'category':<21}{'status':<13}{'claimed':>9}{'eligible':>10}  note")
    for i in claim.items:
        note = (i.reasons[0] if i.reasons else "")[:52]
        print(
            f"{i.file[:25]:<26}{i.category[:20]:<21}{i.status.value:<13}"
            f"{(i.total_inr or 0):>9,.0f}{i.eligible_inr:>10,.0f}  {note}"
        )
    print(
        f"\nclaim state: {claim.state.value}   claimed INR {claim.claimed_inr:,.0f}   "
        f"eligible INR {claim.eligible_inr:,.0f}   counts {claim.counts}"
    )
    print(f"{len(claim.questions)} questions for {len(paths)} receipts:")
    for q in claim.questions:
        print(f"  [{q.kind}] {q.text[:120]}")

    # ---- scoring against ground truth ----
    fields = {"vendor": [0, 0], "date": [0, 0], "total": [0, 0], "currency": [0, 0]}
    cat = [0, 0]
    for e in extracted:
        t = truth.get(e.source_file)
        if t is None:
            continue
        r = e.receipt
        got = {
            "vendor": (r.vendor or "").casefold() if r else None,
            "date": r.receipt_date.isoformat() if r and r.receipt_date else None,
            "total": r.total if r else None,
            "currency": r.currency if r else None,
        }
        want = {"vendor": t["vendor"].casefold(), "date": t["date"], "total": t["total"], "currency": t["currency"]}
        for f in fields:
            ok = abs(got[f] - want[f]) < 0.01 if f == "total" and got[f] is not None else got[f] == want[f]
            fields[f][0] += ok
            fields[f][1] += 1
        cat[0] += cls[e.source_file].category == t["category"]
        cat[1] += 1

    flagged_dup = {i.file for i in claim.items if i.status is ItemStatus.DUPLICATE}
    true_dup = {f for f, t in truth.items() if t["duplicate_of"]} & {p.name for p in paths}
    flagged_inel = {i.file for i in claim.items if i.status is ItemStatus.INELIGIBLE}
    expected_inel = EXPECTED_INELIGIBLE & {p.name for p in paths}

    print("\naccuracy vs ground truth")
    for f, (ok, n) in fields.items():
        print(f"  extraction {f:<9} {pct(ok, n)}")
    print(f"  classification     {pct(*cat)}")
    dup_hits, inel_hits = flagged_dup & true_dup, flagged_inel & expected_inel
    print(f"  duplicates found   {pct(len(dup_hits), len(true_dup))}, false alarms {len(flagged_dup - true_dup)}")
    inel_false_alarms = len(flagged_inel - expected_inel)
    print(f"  ineligible found   {pct(len(inel_hits), len(expected_inel))}, false alarms {inel_false_alarms}")

    out = ROOT / "data" / "eval" / f"{_slug(settings.llm_model)}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "model": settings.llm_model,
                "receipts": len(paths),
                "extraction_accuracy": {f: ok / n for f, (ok, n) in fields.items() if n},
                "classification_accuracy": cat[0] / cat[1] if cat[1] else None,
                "duplicates_found": len(flagged_dup & true_dup),
                "duplicates_expected": len(true_dup),
                "duplicate_false_alarms": len(flagged_dup - true_dup),
                "ineligible_found": len(flagged_inel & expected_inel),
                "ineligible_expected": len(expected_inel),
                "claim_state": claim.state.value,
                "questions": len(claim.questions),
                "claimed_inr": claim.claimed_inr,
                "eligible_inr": claim.eligible_inr,
                "counts": claim.counts,
            },
            indent=2,
        )
    )
    print(f"\nmetrics written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except UserError as e:
        sys.exit(f"Configuration error: {e}")
