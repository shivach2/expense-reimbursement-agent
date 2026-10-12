# A3 — verbatim source: tools and frontend

Create every file below at the given path with **exactly** the content between the fences (the fence lines themselves are not part of the file). Each file ends with a single trailing newline. Do not change anything. Create missing folders as needed. A file marked `(empty file)` must be created empty. Some fences are four backticks long because the file itself contains three-backtick code blocks; the fence that closes a file has the same length as the one that opened it.

### FILE: tools/generate_receipts.py  (360 lines)

```python
"""Generate synthetic receipts + ground truth for the Expense Agent.

All merchants, amounts and dates are invented. Run:
    python tools/generate_receipts.py
Outputs to data/synthetic/receipts/ and data/synthetic/ground_truth.json.
"""

from __future__ import annotations

import json
import random
import shutil
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "synthetic"
RECEIPTS = OUT / "receipts"
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]

random.seed(42)


@dataclass
class Spec:
    file: str
    vendor: str
    date: str | None  # ISO YYYY-MM-DD, None = date missing on receipt
    items: list[tuple[str, float]]
    category: str
    scenario: str
    currency: str = "INR"
    tax_rate: float = 0.05
    fmt: str = "png"  # png | pdf
    look: str = "clean"  # clean | photo | blurry | crumpled
    note: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def subtotal(self) -> float:
        return round(sum(p for _, p in self.items), 2)

    @property
    def tax(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax, 2)


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in FONT_PATHS:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def fmt_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{d}/{m}/{y}"


def render(spec: Spec) -> Image.Image:
    f, fb = font(22), font(28)
    lines: list[tuple[str, ImageFont.ImageFont, str]] = [
        (spec.vendor.upper(), fb, "c"),
        ("Tel: 000-000-0000", f, "c"),
        ("-" * 32, f, "c"),
    ]
    if spec.date:
        lines.append((f"Date: {fmt_date(spec.date)}", f, "l"))
    bill_no = 1000 + zlib.crc32(f"{spec.vendor}{spec.date}{spec.total}".encode()) % 9000
    lines.append((f"Bill No: {bill_no}", f, "l"))
    lines.append(("-" * 32, f, "c"))
    sym = {"INR": "Rs", "USD": "$", "EUR": "EUR", "SGD": "S$"}[spec.currency]
    for name, price in spec.items:
        lines.append((f"{name[:20]:<20}{price:>9.2f}", f, "l"))
    lines.append(("-" * 32, f, "c"))
    lines.append((f"{'Subtotal':<20}{spec.subtotal:>9.2f}", f, "l"))
    lines.append((f"{'Tax':<20}{spec.tax:>9.2f}", f, "l"))
    lines.append((f"{'TOTAL ' + sym:<12}{spec.total:>11.2f}", fb, "l"))
    lines.append(("Paid: CARD ****1234", f, "l"))
    lines.append(("Thank you!", f, "c"))

    w, h = 520, 90 + 38 * len(lines)
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    y = 30
    for text, fnt, align in lines:
        tw = d.textlength(text, font=fnt)
        x = (w - tw) / 2 if align == "c" else 30
        d.text((x, y), text, fill="black", font=fnt)
        y += 38
    return img


def degrade(img: Image.Image, look: str, seed: int) -> Image.Image:
    rnd = random.Random(seed)
    if look == "clean":
        return img
    bg = Image.new("RGB", (img.width + 160, img.height + 160), (110, 90, 70))
    bg.paste(img, (80, 80))
    span = (3, 12) if look == "crumpled" else (3, 7)
    angle = rnd.choice([-1, 1]) * rnd.uniform(*span)
    out = bg.rotate(angle, expand=True, fillcolor=(110, 90, 70), resample=Image.BICUBIC)
    if look == "blurry":
        out = out.filter(ImageFilter.GaussianBlur(2.2))
    if look == "crumpled":
        d = ImageDraw.Draw(out)
        for _ in range(14):
            x1, y1 = rnd.randint(0, out.width), rnd.randint(0, out.height)
            d.line(
                [(x1, y1), (x1 + rnd.randint(-200, 200), y1 + rnd.randint(-60, 60))],
                fill=(190, 190, 190),
                width=rnd.randint(1, 3),
            )
        out = out.filter(ImageFilter.GaussianBlur(0.8))
    # noise-ish: slight brightness variation via blend with gray
    out = Image.blend(out, Image.new("RGB", out.size, (128, 128, 128)), 0.08)
    return out


SPECS: list[Spec] = [
    Spec(
        "r01_cafe.png",
        "Bluebird Cafe",
        "2026-09-14",
        [("Filter Coffee", 90), ("Sandwich", 220), ("Muffin", 100)],
        "meals",
        "clean",
    ),
    Spec("r02_taxi.png", "Zippy Cabs", "2026-09-14", [("Ride #4821", 640)], "local_transport", "clean", tax_rate=0.0),
    Spec(
        "r03_hotel.pdf",
        "Lotus Grove Hotel",
        "2026-09-15",
        [("Room 1 night", 5800), ("Breakfast", 600)],
        "lodging",
        "clean",
        tax_rate=0.12,
        fmt="pdf",
    ),
    Spec(
        "r04_dinner_photo.png",
        "Saffron Table",
        "2026-09-15",
        [("Thali", 450), ("Lassi", 120), ("Dessert", 180)],
        "meals",
        "photo",
        look="photo",
    ),
    Spec(
        "r05_stationery.png",
        "Paperwise Stores",
        "2026-09-16",
        [("Notebook x2", 240), ("Pens", 120)],
        "office_supplies",
        "clean",
        tax_rate=0.18,
    ),
    Spec(
        "r06_blurry_lunch.png",
        "Green Leaf Eatery",
        "2026-09-16",
        [("Bowl", 380), ("Juice", 140)],
        "meals",
        "blurry",
        look="blurry",
    ),
    Spec(
        "r07_crumpled_fuel.png",
        "Highway Fuel Point",
        "2026-09-17",
        [("Petrol 20L", 2100)],
        "fuel",
        "crumpled",
        look="crumpled",
        tax_rate=0.0,
    ),
    Spec(
        "r08_foreign_usd.png",
        "Harbor Grill",
        "2026-09-18",
        [("Burger", 14.5), ("Fries", 5), ("Soda", 3)],
        "meals",
        "foreign_currency",
        currency="USD",
        tax_rate=0.08,
    ),
    Spec(
        "r09_foreign_sgd.pdf",
        "Marina Bay Taxi",
        "2026-09-18",
        [("Airport transfer", 32)],
        "local_transport",
        "foreign_currency",
        currency="SGD",
        tax_rate=0.09,
        fmt="pdf",
    ),
    Spec(
        "r10_missing_date.png",
        "Corner Stationers",
        None,
        [("Printer paper", 150), ("Stapler", 90)],
        "office_supplies",
        "missing_date",
        tax_rate=0.12,
    ),
    Spec(
        "r11_overlimit_meal.png",
        "Grand Terrace Dining",
        "2026-09-19",
        [("Tasting menu x4", 7200), ("Wine", 3800)],
        "meals",
        "over_limit",
        look="photo",
        tax_rate=0.18,
    ),
    Spec("r12_old_receipt.png", "Sunrise Bakery", "2026-03-02", [("Cake", 650)], "meals", "out_of_window"),
    Spec(
        "r13_parking.png",
        "City Park Lot",
        "2026-09-20",
        [("Parking 3h", 120)],
        "local_transport",
        "clean",
        tax_rate=0.0,
    ),
    Spec(
        "r14_conf_fee.pdf",
        "NovaTech Summit",
        "2026-09-21",
        [("Conference pass", 9500)],
        "training",
        "clean",
        tax_rate=0.18,
        fmt="pdf",
    ),
    Spec(
        "r15_train.png",
        "RailLink Express",
        "2026-09-22",
        [("Ticket AC chair", 1250)],
        "local_transport",
        "clean",
        tax_rate=0.05,
        look="photo",
    ),
    Spec(
        "r16_internet.pdf",
        "SwiftNet Broadband",
        "2026-09-01",
        [("Monthly plan", 999)],
        "communication",
        "clean",
        tax_rate=0.18,
        fmt="pdf",
    ),
    Spec("r17_taxi2.png", "Zippy Cabs", "2026-09-22", [("Ride #5530", 410)], "local_transport", "clean", tax_rate=0.0),
    Spec(
        "r18_lunch_client.png",
        "Olive & Oak",
        "2026-09-23",
        [("Client lunch x3", 2100), ("Drinks", 540)],
        "client_entertainment",
        "client_meal",
        tax_rate=0.05,
        look="photo",
    ),
    Spec(
        "r19_hotel2.png", "Lotus Grove Hotel", "2026-09-23", [("Room 1 night", 5800)], "lodging", "clean", tax_rate=0.12
    ),
    Spec(
        "r24_pharmacy.png",
        "Corner Pharmacy",
        "2026-09-18",
        [("Cough syrup", 140), ("Vitamins", 260)],
        "personal_expenses",
        "personal_expense",
        tax_rate=0.12,
    ),
    Spec("r20_coffee2.png", "Bluebird Cafe", "2026-09-24", [("Cappuccino", 160)], "meals", "clean"),
]

# duplicates: (new file, source file, kind)
DUPLICATES = [
    ("r21_dup_exact_cafe.png", "r01_cafe.png", "exact_duplicate"),
    ("r22_dup_photo_dinner.png", "r04_dinner_photo.png", "near_duplicate"),
    ("r23_dup_taxi_photo.png", "r02_taxi.png", "near_duplicate"),
]


def save(img: Image.Image, path: Path, fmt: str) -> None:
    if fmt == "pdf":
        img.save(path, "PDF", resolution=100)
    else:
        img.save(path)


def main() -> None:
    if RECEIPTS.exists():
        shutil.rmtree(RECEIPTS)
    RECEIPTS.mkdir(parents=True)
    truth: list[dict] = []
    specs_by_file: dict[str, Spec] = {}

    for i, s in enumerate(SPECS):
        img = degrade(render(s), s.look, seed=100 + i)
        save(img, RECEIPTS / s.file, s.fmt)
        specs_by_file[s.file] = s
        truth.append(
            {
                "file": s.file,
                "vendor": s.vendor,
                "date": s.date,
                "total": s.total,
                "tax": s.tax,
                "currency": s.currency,
                "category": s.category,
                "scenario": s.scenario,
                "duplicate_of": None,
            }
        )

    for new, src, kind in DUPLICATES:
        s = specs_by_file[src]
        if kind == "exact_duplicate":
            shutil.copy(RECEIPTS / src, RECEIPTS / new)
        else:  # re-photographed: same content, different angle/noise
            img = degrade(render(s), "photo", seed=999 + len(new))
            save(img, RECEIPTS / new, "png")
        truth.append(
            {
                "file": new,
                "vendor": s.vendor,
                "date": s.date,
                "total": s.total,
                "tax": s.tax,
                "currency": s.currency,
                "category": s.category,
                "scenario": kind,
                "duplicate_of": src,
            }
        )

    (OUT / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    print(f"Wrote {len(truth)} receipts to {RECEIPTS}")


if __name__ == "__main__":
    main()
```

### FILE: tools/extract_receipts.py  (94 lines)

```python
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
```

### FILE: tools/run_pipeline.py  (146 lines)

```python
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
```

### FILE: tools/make_deck.py  (423 lines)

```python
"""Build the 10-slide PowerPoint deck (docs/Expense_Agent_Deck.pptx) with python-pptx.

    pip install python-pptx
    python tools/make_deck.py

Screenshots in docs/screenshots/ are optional: a missing screenshot is replaced by a grey placeholder note, so
the deck still builds on a machine where the screenshots were not copied. Take fresh screenshots of the running
app and save them under the same names to fill the placeholders.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
SS = ROOT / "docs" / "screenshots"
OUT = ROOT / "docs" / "Expense_Agent_Deck.pptx"

INK, MUTE, BLUE = RGBColor(0x1C, 0x23, 0x30), RGBColor(0x66, 0x70, 0x85), RGBColor(0x1D, 0x4E, 0xD8)
LIGHT, LIGHTER, AMBER = RGBColor(0xEE, 0xF2, 0xFF), RGBColor(0xDB, 0xE4, 0xFF), RGBColor(0xB5, 0x47, 0x08)
WHITE = RGBColor(255, 255, 255)

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def text(slide, x, y, w, h, content, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, line in enumerate(content if isinstance(content, list) else [content]):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(8)
        r = p.add_run()
        r.text, r.font.size, r.font.bold, r.font.color.rgb, r.font.name = line, Pt(size), bold, color, "Calibri"
    return tb


def bullets(slide, x, y, w, h, items, size=18):
    """Items written as 'Bold lead — grey detail' render the lead in bold."""
    tf = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)).text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(10)
        head, _, rest = item.partition(" — ")
        r = p.add_run()
        r.text, r.font.size, r.font.bold, r.font.color.rgb, r.font.name = (
            "•  " + head,
            Pt(size),
            bool(rest),
            INK,
            "Calibri",
        )
        if rest:
            r2 = p.add_run()
            r2.text, r2.font.size, r2.font.color.rgb, r2.font.name = " — " + rest, Pt(size), MUTE, "Calibri"


def title(slide, t, sub=None):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.25), prs.slide_height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = BLUE
    bar.line.fill.background()
    text(slide, 0.7, 0.4, 12, 0.9, t, 32, True)
    if sub:
        text(slide, 0.7, 1.15, 12, 0.5, sub, 16, False, MUTE)


def panel(slide, x, y, w, h, fill=LIGHT):
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    box.fill.solid()
    box.fill.fore_color.rgb = fill
    box.line.fill.background()
    return box


def picture(slide, name, x, y, w, h, caption=None):
    path = SS / name
    if not path.exists():
        panel(slide, x, y, w, h, RGBColor(0xF2, 0xF4, 0xF7))
        text(
            slide,
            x + 0.3,
            y + h / 2 - 0.4,
            w - 0.6,
            1,
            f"[screenshot placeholder: {name}]",
            14,
            False,
            MUTE,
            PP_ALIGN.CENTER,
        )
        return
    iw, ih = Image.open(path).size
    s = min(w / iw, h / ih)
    pw, ph = iw * s, ih * s
    pic = slide.shapes.add_picture(str(path), Inches(x + (w - pw) / 2), Inches(y), Inches(pw), Inches(ph))
    pic.line.color.rgb = RGBColor(0xD0, 0xD5, 0xDD)
    if caption:
        text(slide, x, y + ph + 0.05, w, 0.4, caption, 12, False, MUTE, PP_ALIGN.CENTER)


def table(slide, x, y, w, rows, col_w, size=14, row_h=0.5):
    t = slide.shapes.add_table(
        len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows))
    ).table
    for j, cw in enumerate(col_w):
        t.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = t.cell(i, j)
            c.text = val
            c.margin_left = c.margin_right = Inches(0.08)
            for p in c.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size, r.font.name, r.font.bold = Pt(size), "Calibri", i == 0
                    r.font.color.rgb = WHITE if i == 0 else INK
            c.fill.solid()
            c.fill.fore_color.rgb = BLUE if i == 0 else (RGBColor(0xF8, 0xF9, 0xFC) if i % 2 else WHITE)


# 1 ---- title
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
bg.fill.solid()
bg.fill.fore_color.rgb = BLUE
bg.line.fill.background()
text(s, 0.9, 2.2, 11.5, 1.2, "Expense & Reimbursement Agent", 46, True, WHITE)
text(
    s,
    0.9,
    3.5,
    11.5,
    1,
    "An AI that reads the bills and reads the policy — from a pile of receipts to ready to submit",
    22,
    False,
    LIGHTER,
)
text(
    s,
    0.9,
    6.3,
    11.5,
    0.6,
    "Competition prototype · all data synthetic · Pydantic AI + Claude · FastAPI",
    14,
    False,
    LIGHTER,
)

# 2 ---- problem
s = prs.slides.add_slide(BLANK)
title(s, "The problem", "Reimbursement is a tax on every employee and every finance reviewer")
bullets(
    s,
    0.7,
    1.9,
    7.2,
    4.8,
    [
        "Collect and key in bills — photos, PDFs, foreign currency, crumpled paper",
        "Categorise each one — and guess which policy bucket it belongs in",
        "Look up the limits — policies live in long documents that change",
        "Avoid duplicates and missing details — or the claim bounces back",
        "Re-submit after rejection — the employee finds out too late",
    ],
    20,
)
panel(s, 8.4, 2.1, 4.4, 3.8)
box = text(
    s,
    8.7,
    2.3,
    3.9,
    3.4,
    [
        "Our goal",
        "Drop in the bills. Get a policy-checked, explained, submission-ready claim — "
        "answering only what the system cannot work out itself.",
    ],
    18,
)
box.text_frame.paragraphs[0].runs[0].font.bold = True
box.text_frame.paragraphs[0].runs[0].font.color.rgb = BLUE

# 3 ---- flow
s = prs.slides.add_slide(BLANK)
title(s, "How it works", "Six steps, three of them use AI")
steps = [
    ("1", "Drop bills", "photos, PDFs"),
    ("2", "AI reads bills", "vendor, date, total, items"),
    ("3", "AI reads policy", "limits, grades, clauses"),
    ("4", "Classify & check", "category, eligible amount, duplicates"),
    ("5", "Ask only gaps", "5 questions, not 24 forms"),
    ("6", "Submit", "mock finance system"),
]
for i, (n, h, sub) in enumerate(steps):
    x = 0.7 + i * 2.07
    panel(s, x, 2.4, 1.9, 2.6, LIGHTER if i in (1, 2, 3) else LIGHT)
    text(s, x + 0.1, 2.5, 1.7, 0.6, n, 30, True, BLUE, PP_ALIGN.CENTER)
    text(s, x + 0.1, 3.2, 1.7, 0.7, h, 17, True, INK, PP_ALIGN.CENTER)
    text(s, x + 0.1, 3.95, 1.7, 1.0, sub, 13, False, MUTE, PP_ALIGN.CENTER)
text(
    s,
    0.7,
    5.5,
    12,
    1.2,
    "Steps 2–4 use LLMs; every amount is computed by deterministic code, and every AI-extracted rule "
    "must quote the policy verbatim.",
    17,
)

# 4 ---- AI vs deterministic
s = prs.slides.add_slide(BLANK)
title(s, "Where AI is used — and where it is not", "LLMs interpret and judge; plain code does the money")
table(
    s,
    0.7,
    1.9,
    11.9,
    [
        ["Component", "Technique", "Why"],
        ["Receipt extraction", "LLM (vision)", "Messy photos and PDFs"],
        [
            "Policy interpretation",
            "LLM + grounding check",
            "Prose in, structured limits out; quotes stop invented rules",
        ],
        ["Clause lookup for answers", "RAG (BM25 over clauses)", "Cites the exact clause; offline and free"],
        ["Bill classification", "LLM with reasoning", "A judgement call that must be explained"],
        ["Eligible amount, caps, partial pay", "Deterministic", "Financial accuracy, reproducible"],
        ["Duplicates, grouping, claim state", "Deterministic", "Auditable (image hashing was tested and rejected)"],
        ["Chat assistant", "Agent with tools", "Open-ended follow-ups; reads decisions, never makes them"],
    ],
    [3.7, 3.0, 5.2],
    15,
    0.58,
)

# 5 ---- policy as documents
s = prs.slides.add_slide(BLANK)
title(s, "Policy is a document, not code", "Edit one sentence — the claim updates, no release needed")
bullets(
    s,
    0.7,
    1.9,
    5.0,
    4.8,
    [
        "AI reads the policy files — limits, grades, units, partial-pay rules",
        "Each rule carries a verbatim quote — checked against the clause; numbers must appear in the quote",
        "Hotel limit 5,000 → 7,000 — reimbursable total moves ₹23,053 → ₹26,549",
        "No code changed — interpretation is cached by document hash",
    ],
    17,
)
picture(
    s,
    "04_policy_changed_no_code.jpg",
    6.0,
    1.8,
    6.9,
    5.0,
    "Policy tab: the AI-extracted limit now reads ₹7,000 per night",
)

# 6 ---- explainable
s = prs.slides.add_slide(BLANK)
title(s, "Every decision is explained", "Category, clause, quote, arithmetic and what is still needed")
picture(s, "02_explainable_decision.jpg", 0.7, 1.8, 7.6, 5.0)
bullets(
    s,
    8.6,
    1.9,
    4.4,
    4.8,
    [
        "Why this category — the AI's reasoning",
        "Which clause — TEP-2.1 and GE-2.2, with quotes",
        "What is eligible — ₹5,000 of ₹7,168; excess not reimbursable",
        "What is needed — shown as a question, once",
    ],
    16,
)

# 7 ---- experience
s = prs.slides.add_slide(BLANK)
title(s, "The experience", "Chat on the left, claim on the right")
picture(s, "01_claim_and_chat.jpg", 0.5, 1.8, 6.4, 4.6, "24 bills read; 5 questions; submit disabled until ready")
picture(s, "05_submitted.jpg", 7.1, 1.8, 5.8, 4.6, "Submitted to the mock finance system, with a reference")

# 8 ---- results
s = prs.slides.add_slide(BLANK)
title(s, "Results on 24 synthetic receipts", "Measured with Claude Sonnet 5.5; 133 automated tests pass, 100% coverage")
table(
    s,
    0.7,
    1.9,
    8.0,
    [
        ["Measure", "Result"],
        ["Vendor, date, total, currency extracted", "24 / 24"],
        ["Category classification", "23 / 24"],
        ["Duplicates found (incl. re-photographed)", "3 / 3, no false alarms"],
        ["Bills auto-excluded with clause", "3 (expired, personal, over limit)"],
        ["Questions asked", "5 for 24 receipts"],
        ["Policy edit applied without code", "Yes"],
    ],
    [5.0, 3.0],
    16,
    0.56,
)
panel(s, 9.2, 1.9, 3.6, 3.9)
box = text(
    s,
    9.4,
    2.1,
    3.2,
    3.6,
    [
        "Free-tier check",
        "Gemini 3.8 Flash interpreted the policy identically; the 5 receipts it processed were "
        "all correct. 3 hit HTTP 503 overload, so no full-set figure is claimed.",
    ],
    14,
)
box.text_frame.paragraphs[0].runs[0].font.bold = True
box.text_frame.paragraphs[0].runs[0].font.size = Pt(18)

# 9 ---- impact
s = prs.slides.add_slide(BLANK)
title(s, "Business impact", "Illustrative model — assumptions are stated and editable")
table(
    s,
    0.7,
    1.9,
    7.2,
    [
        ["24 receipts", "Time"],
        ["Manual (assume 4 min per receipt)", "~96 min"],
        ["With the agent (5 answers + 3 min review)", "~7 min"],
        ["Saved per claim", "~89 min (≈90%)"],
    ],
    [4.6, 2.6],
    16,
    0.62,
)
bullets(
    s,
    8.3,
    1.9,
    4.6,
    4.8,
    [
        "Fewer rejected claims — employees see the eligible amount first",
        "Reviewers stop re-checking limits and duplicates",
        "Policy changes ship as a document edit",
        "Full audit trail — clause, quote and maths per item",
    ],
    16,
)
text(
    s,
    0.7,
    5.0,
    7.2,
    1.5,
    "Time figures come from an assumption (4 min per receipt by hand, 30 s per question), "
    "not from measurement. See docs/BUSINESS_IMPACT.md.",
    13,
    False,
    AMBER,
)

# 10 --- limits
s = prs.slides.add_slide(BLANK)
title(s, "Honest limits and next steps")
bullets(
    s,
    0.7,
    1.7,
    6.0,
    5,
    [
        "Synthetic bills only — real receipts are messier",
        "One employee profile and one policy set",
        "Static illustrative FX rates; no authentication",
        "Policy parsing assumes numbered clauses",
        "Free LLM tiers rate-limit; results are cached",
    ],
    18,
)
bullets(
    s,
    7.0,
    1.7,
    5.8,
    5,
    [
        "Next — real HRMS grades and location tiers",
        "Next — embeddings RAG for large policy libraries",
        "Next — multi-category bills and trip-level caps",
        "Next — approval workflow and finance integration",
    ],
    18,
)

OUT.parent.mkdir(parents=True, exist_ok=True)
prs.save(OUT)
print(f"saved {OUT.relative_to(ROOT)} ({len(prs.slides)} slides)")
```

### FILE: frontend/index.html  (343 lines)

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Expense & Reimbursement Agent</title>
<style>
  :root { --bg:#f5f6f8; --card:#fff; --ink:#1c2330; --mute:#667085; --line:#e4e7ec; --brand:#1d4ed8; --brand-ink:#fff;
          --ok:#067647; --ok-bg:#ecfdf3; --warn:#b54708; --warn-bg:#fffaeb; --bad:#b42318; --bad-bg:#fef3f2; --grey-bg:#f2f4f7; }
  * { box-sizing:border-box; }
  body { margin:0; font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; color:var(--ink); background:var(--bg); }
  header { background:var(--card); border-bottom:1px solid var(--line); padding:10px 20px; display:flex; align-items:center; gap:20px; flex-wrap:wrap; }
  header h1 { font-size:16px; margin:0; }
  .who { color:var(--mute); font-size:13px; }
  nav { margin-left:auto; display:flex; gap:4px; }
  nav button { border:0; background:none; padding:7px 14px; border-radius:8px; font:inherit; cursor:pointer; color:var(--mute); }
  nav button[aria-selected=true] { background:var(--grey-bg); color:var(--ink); font-weight:600; }
  main { display:grid; grid-template-columns:minmax(300px,380px) 1fr; gap:16px; padding:16px 20px; max-width:1500px; margin:0 auto; }
  @media (max-width:900px) { main { grid-template-columns:1fr; } }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px; }
  .card h2 { font-size:14px; margin:0 0 10px; }
  button.primary { background:var(--brand); color:var(--brand-ink); border:0; padding:8px 14px; border-radius:8px; font:inherit; font-weight:600; cursor:pointer; }
  button.primary:disabled { background:#98a2b3; cursor:not-allowed; }
  button.ghost { background:#fff; border:1px solid var(--line); padding:7px 12px; border-radius:8px; font:inherit; cursor:pointer; }
  input,select,textarea { font:inherit; padding:7px 9px; border:1px solid #cfd4dc; border-radius:8px; max-width:100%; }
  :focus-visible { outline:2px solid var(--brand); outline-offset:1px; }
  /* chat */
  #chat { display:flex; flex-direction:column; height:calc(100vh - 100px); position:sticky; top:12px; }
  #msgs { flex:1; overflow:auto; display:flex; flex-direction:column; gap:8px; padding:4px 2px; }
  .bub { padding:8px 11px; border-radius:12px; max-width:92%; white-space:pre-wrap; }
  .bub.user { background:var(--brand); color:#fff; align-self:flex-end; border-bottom-right-radius:3px; }
  .bub.bot { background:var(--grey-bg); align-self:flex-start; border-bottom-left-radius:3px; }
  .chips { display:flex; gap:6px; flex-wrap:wrap; margin:8px 0; }
  .chips button { border:1px solid var(--line); background:#fff; border-radius:999px; padding:4px 10px; font-size:12px; cursor:pointer; }
  #chatform { display:flex; gap:6px; }
  #chatform input { flex:1; }
  /* claim */
  .drop { border:2px dashed #b9c0cc; border-radius:12px; padding:18px; text-align:center; color:var(--mute); background:#fcfcfd; }
  .drop.over { border-color:var(--brand); background:#eff4ff; }
  .row { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }
  .grow { flex:1; }
  .bar { height:8px; background:var(--grey-bg); border-radius:99px; overflow:hidden; }
  .bar > i { display:block; height:100%; background:var(--brand); transition:width .3s; }
  .chip { display:inline-block; padding:1px 9px; border-radius:99px; font-size:12px; font-weight:600; }
  .chip.complete,.chip.ready { background:var(--ok-bg); color:var(--ok); }
  .chip.missing_info,.chip.questionable,.chip.needs_input { background:var(--warn-bg); color:var(--warn); }
  .chip.ineligible,.chip.blocked { background:var(--bad-bg); color:var(--bad); }
  .chip.duplicate { background:var(--grey-bg); color:var(--mute); }
  .chip.cat { background:#eef2ff; color:#3538cd; font-weight:500; }
  .kpis { display:flex; gap:22px; flex-wrap:wrap; }
  .kpi b { display:block; font-size:20px; } .kpi span { color:var(--mute); font-size:12px; }
  .q { border:1px solid var(--line); border-radius:10px; padding:10px; margin-bottom:8px; background:#fffdf5; }
  .q .row { margin-top:6px; }
  .grp { margin:14px 0 6px; font-weight:600; display:flex; justify-content:space-between; }
  .item { display:grid; grid-template-columns:56px 1fr auto; gap:10px; padding:10px 0; border-top:1px solid var(--line); }
  .item img { width:56px; height:72px; object-fit:cover; border-radius:6px; border:1px solid var(--line); background:var(--grey-bg); }
  .amt { text-align:right; white-space:nowrap; } .amt small { color:var(--mute); display:block; }
  .why { grid-column:2 / 4; font-size:13px; color:#344054; background:var(--grey-bg); border-radius:8px; padding:8px 10px; display:none; }
  .why.open { display:block; } .why blockquote { margin:6px 0 0; padding-left:8px; border-left:3px solid #98a2b3; color:#475467; }
  .linkbtn { background:none; border:0; color:var(--brand); cursor:pointer; padding:0; font:inherit; }
  .muted { color:var(--mute); } .excl .item { opacity:.8; }
  .banner { padding:10px 12px; border-radius:10px; margin-bottom:10px; }
  .banner.ok { background:var(--ok-bg); color:var(--ok); } .banner.err { background:var(--bad-bg); color:var(--bad); }
  table { border-collapse:collapse; width:100%; } th,td { text-align:left; padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { color:var(--mute); font-weight:500; font-size:12px; }
  textarea.doc { width:100%; height:300px; font:12.5px/1.5 ui-monospace,Menlo,monospace; }
  .hidden { display:none !important; }
</style>
</head>
<body>
<header>
  <h1>Expense &amp; Reimbursement Agent</h1>
  <span class="who" id="who"></span>
  <nav role="tablist" aria-label="Sections">
    <button role="tab" data-tab="claim" aria-selected="true">Claim</button>
    <button role="tab" data-tab="policy" aria-selected="false">Policy (AI-interpreted)</button>
    <button role="tab" data-tab="finance" aria-selected="false">Finance system</button>
  </nav>
</header>

<main id="tab-claim">
  <section class="card" id="chat" aria-label="Assistant chat">
    <h2>Assistant</h2>
    <div id="msgs" aria-live="polite"></div>
    <div class="chips" id="chips"></div>
    <form id="chatform"><input id="chatin" aria-label="Message the assistant" placeholder="Ask about your claim…" autocomplete="off"><button class="primary" id="chatsend">Send</button></form>
  </section>
  <section id="claimcol"></section>
</main>

<main id="tab-policy" class="hidden" style="grid-template-columns:1fr 1fr"></main>
<main id="tab-finance" class="hidden" style="grid-template-columns:1fr"></main>

<script>
"use strict";
const $ = (s, r=document) => r.querySelector(s);
const state = { sid:null, snap:null, policy:null, poll:null, openWhy:new Set(), busy:false };

function el(tag, attrs={}, ...kids) {
  const e = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "html") throw new Error("no innerHTML");
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(String(c)));
  return e;
}
const inr = n => n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const STATUS = { complete:"Complete", missing_info:"Needs info", questionable:"Needs review", duplicate:"Duplicate", ineligible:"Not reimbursable" };
const STATE = { ready:"Ready to submit", needs_input:"Needs your input", blocked:"Nothing claimable" };
const docCode = n => n.replace(/\.md$/,"").split("_").map(w => w[0]).join("").toUpperCase();

async function api(path, opts={}) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || `Request failed (${r.status})`);
  return body;
}
const post = (p, b) => api(p, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(b ?? {}) });

/* ------------------------------ session ------------------------------ */
async function init() {
  state.snap = await api("/api/sessions", { method:"POST" });
  state.sid = state.snap.id;
  $("#who").textContent = `${state.snap.employee.name} · grade ${state.snap.employee.grade} · ${state.snap.employee.role}`;
  say("bot", "Hi! Drop in your bills (photos or PDFs) and I'll build the claim, check it against the policy, and ask only what I can't work out myself.");
  renderChips(); render();
}
function setSnap(s) { state.snap = s; render(); }
function startPolling() {
  clearInterval(state.poll);
  state.poll = setInterval(async () => {
    try { const s = await api(`/api/sessions/${state.sid}`); setSnap(s);
      if (s.status !== "processing") { clearInterval(state.poll); if (s.status === "ready") onReady(s); } }
    catch (e) { clearInterval(state.poll); banner(e.message, true); }
  }, 700);
}
function onReady(s) {
  const c = s.claim; if (!c) return;
  say("bot", `Done. ${c.items.length} receipts read. ${c.counts.duplicate || 0} duplicate(s) and ${c.counts.ineligible || 0} not reimbursable were left out. ` +
    (c.questions.length ? `I need ${c.questions.length} thing(s) from you — they're listed on the right.` : "Nothing else needed — you can submit."));
}
async function upload(files) {
  if (!files.length) return;
  const fd = new FormData(); for (const f of files) fd.append("files", f);
  try { setSnap(await api(`/api/sessions/${state.sid}/receipts`, { method:"POST", body: fd })); startPolling(); }
  catch (e) { banner(e.message, true); }
}
async function loadDemo() {
  try { setSnap(await post(`/api/sessions/${state.sid}/demo`)); startPolling(); } catch (e) { banner(e.message, true); }
}
async function answer(kind, target, value) {
  try { setSnap(await post(`/api/sessions/${state.sid}/answers`, { kind, target, value })); }
  catch (e) { banner(e.message, true); throw e; }
}
async function submit() {
  try { const r = await post(`/api/sessions/${state.sid}/submit`); setSnap(r.session);
    say("bot", `Submitted to the finance system as ${r.submission.id}. Eligible reimbursement: ${inr(r.submission.eligible_inr)}.`); }
  catch (e) { banner(e.message, true); }
}
function banner(text, err) {
  const b = el("div", { class:"banner " + (err ? "err" : "ok"), role:"alert" }, text);
  $("#claimcol").prepend(b); setTimeout(() => b.remove(), 6000);
}

/* ------------------------------ chat ------------------------------ */
const rich = t => String(t).split("**").map((p, i) => i % 2 ? el("b", {}, p) : p);  // **bold** only; no HTML
function say(who, text) {
  const b = el("div", { class:"bub " + who }, who === "bot" ? rich(text) : text);
  $("#msgs").append(b); $("#msgs").scrollTop = 1e9; return b;
}
function renderChips() {
  const box = $("#chips"); box.replaceChildren();
  for (const t of ["What's still missing?", "Why was my hotel reduced?", "What's the meal limit?", "Which bills were left out?"])
    box.append(el("button", { type:"button", onclick:() => sendChat(t) }, t));
}
async function sendChat(text) {
  if (!text.trim() || state.busy) return;
  if (!state.snap.claim) { say("bot", "Upload some receipts first and then I can help with the claim."); return; }
  state.busy = true; $("#chatsend").disabled = true;
  say("user", text); const wait = say("bot", "…");
  try { const r = await post(`/api/sessions/${state.sid}/chat`, { message: text }); wait.replaceChildren(...rich(r.reply)); setSnap(r.session); }
  catch (e) { wait.textContent = "Sorry — " + e.message; }
  finally { state.busy = false; $("#chatsend").disabled = false; }
}
$("#chatform").addEventListener("submit", e => { e.preventDefault(); const v = $("#chatin").value; $("#chatin").value = ""; sendChat(v); });

/* ------------------------------ claim view ------------------------------ */
function render() {
  const s = state.snap, col = $("#claimcol"), keep = [...col.querySelectorAll(".banner")];
  col.replaceChildren(...keep, uploader(s));
  if (s.status === "processing") col.append(progress(s));
  if (s.status === "error") col.append(el("div", { class:"banner err" }, "Processing failed: " + s.error));
  if (s.claim) col.append(summary(s), questions(s), items(s));
}
function uploader(s) {
  const input = el("input", { type:"file", multiple:true, accept:"image/*,.pdf", class:"hidden", "aria-label":"Choose receipt files", onchange:e => upload([...e.target.files]) });
  const zone = el("div", { class:"drop", tabindex:"0", role:"button", "aria-label":"Drop receipts here or press Enter to choose files",
    onclick:() => input.click(), onkeydown:e => { if (e.key === "Enter" || e.key === " ") input.click(); },
    ondragover:e => { e.preventDefault(); zone.classList.add("over"); }, ondragleave:() => zone.classList.remove("over"),
    ondrop:e => { e.preventDefault(); zone.classList.remove("over"); upload([...e.dataTransfer.files]); } },
    el("strong", {}, s.submitted_ref ? "Claim submitted" : "Drop receipts here"), el("div", { class:"muted" }, "photos or PDFs · or click to choose"), input);
  const demo = el("button", { class:"ghost", type:"button", onclick:loadDemo, disabled: s.status === "processing" || !!s.submitted_ref }, "Try with the demo receipts (24 synthetic bills)");
  return el("div", { class:"card", style:"margin-bottom:12px" }, zone, el("div", { style:"margin-top:8px" }, demo));
}
function progress(s) {
  const { done, total } = s.progress, pct = total ? Math.round(100 * done / total) : 0;
  return el("div", { class:"card", style:"margin-bottom:12px", "aria-live":"polite" },
    el("div", {}, `Reading and checking receipts… ${done}/${total}`), el("div", { class:"bar" }, el("i", { style:`width:${pct}%` })));
}
function summary(s) {
  const c = s.claim, kpi = (v, l) => el("div", { class:"kpi" }, el("b", {}, v), el("span", {}, l));
  const canSubmit = c.state === "ready" && !s.submitted_ref && s.status !== "processing";
  return el("div", { class:"card", style:"margin-bottom:12px" },
    el("div", { class:"row" },
      el("span", { class:"chip " + c.state }, s.submitted_ref ? "Submitted · " + s.submitted_ref : STATE[c.state]),
      el("div", { class:"kpis grow" }, kpi(inr(c.claimed_inr), "on the bills"), kpi(inr(c.eligible_inr), "reimbursable under policy"),
        kpi(c.questions.length, "open question(s)")),
      el("button", { class:"primary", disabled:!canSubmit, onclick:submit }, "Submit claim")),
    el("div", { class:"muted", style:"margin-top:6px" }, Object.entries(c.counts).map(([k, v]) => `${v} ${STATUS[k] || k}`).join(" · ")));
}
function questions(s) {
  const qs = s.claim.questions; if (!qs.length || s.submitted_ref) return el("span");
  return el("div", { class:"card", style:"margin-bottom:12px" }, el("h2", {}, `I need ${qs.length} thing(s) from you`), qs.map(q => questionRow(q, s)));
}
function questionRow(q, s) {
  const inputs = [];
  const mk = (kind, type, ph, opts) => { const i = opts ? el("select", { "aria-label": ph }, el("option", { value:"" }, ph), opts.map(o => el("option", { value:o }, o)))
    : el("input", { type, placeholder:ph, "aria-label":ph, size: type === "text" ? 34 : 14 }); inputs.push([kind, i]); return i; };
  let widgets, target = q.target;
  if (q.kind === "purpose") widgets = [mk("purpose_group", "text", "Business purpose, e.g. client visit in Pune")];
  else if (q.kind === "justify") widgets = [mk("justification", "text", "Justification or approval reference")];
  else if (q.kind === "clarify") widgets = [mk("category", "text", "Choose a category", q.options)];
  else if (q.kind === "field") widgets = q.fields.map(f => ({ date:() => mk("date", "date", "Date"), vendor:() => mk("vendor", "text", "Vendor"),
      amount:() => mk("amount", "number", "Amount"), currency:() => mk("currency", "text", "Currency (3 letters)") }[f] || (() => mk(f, "text", f)))());
  else widgets = [];
  const go = el("button", { class:"primary", type:"button", onclick: async () => {
      const vals = inputs.map(([k, i]) => [k, i.value.trim()]).filter(([, v]) => v);
      if (q.kind === "confirm") vals.push(["confirm", "yes"]);
      if (!vals.length) return;
      go.disabled = true;
      try { for (const [k, v] of vals) await answer(k, target, v); } catch { go.disabled = false; }
    } }, q.kind === "confirm" ? "Yes, that's correct" : "Save");
  return el("div", { class:"q" }, el("div", {}, q.text), el("div", { class:"row" }, widgets, go));
}
function items(s) {
  const c = s.claim, byFile = Object.fromEntries(c.items.map(i => [i.file, i]));
  const out = el("div", { class:"card" }, el("h2", {}, "Your claim"));
  const grouped = new Set();
  for (const g of c.groups) {
    out.append(el("div", { class:"grp" }, el("span", {}, g.title), el("span", { class:"muted" }, inr(g.eligible_inr) + " reimbursable")));
    for (const f of g.files) { grouped.add(f); out.append(itemRow(byFile[f], s)); }
  }
  const rest = c.items.filter(i => !grouped.has(i.file) && !["duplicate", "ineligible"].includes(i.status));
  if (rest.length) { out.append(el("div", { class:"grp" }, "Needs a date before it can be grouped")); rest.forEach(i => out.append(itemRow(i, s))); }
  const excl = c.items.filter(i => ["duplicate", "ineligible"].includes(i.status));
  if (excl.length) { out.append(el("div", { class:"grp" }, "Left out of the claim")); const box = el("div", { class:"excl" }); excl.forEach(i => box.append(itemRow(i, s))); out.append(box); }
  return out;
}
function itemRow(i, s) {
  const r = s.receipts[i.file], left = ["duplicate", "ineligible"].includes(i.status);
  const key = i.file, open = state.openWhy.has(key);
  const why = el("div", { class:"why" + (open ? " open" : "") });
  if (i.category_reasoning) why.append(el("div", {}, el("b", {}, "Why this category: "), i.category_reasoning));
  if (i.decision) {
    why.append(el("div", { style:"margin-top:4px" }, el("b", {}, "Policy decision: "), i.decision.explanation));
    for (const c of i.decision.cites) why.append(el("blockquote", {}, `${c.ref} (${c.document}): “${c.quote}”`));
    if (i.decision.needs.length) why.append(el("div", { style:"margin-top:4px" }, el("b", {}, "Needed: "), i.decision.needs.join(", ")));
  }
  for (const rs of i.reasons) if (!i.decision || rs !== i.decision.explanation) why.append(el("div", { class:"muted", style:"margin-top:4px" }, "• " + rs));
  const ex = r && r.extracted.receipt;
  if (ex) why.append(el("div", { class:"muted", style:"margin-top:6px" }, `Read from bill: ${ex.vendor || "?"}, ${ex.receipt_date || "no date"}, ${ex.total ?? "?"} ${ex.currency} · confidence vendor ${ex.confidence.vendor}, date ${ex.confidence.date}, total ${ex.confidence.total}`));
  const toggle = el("button", { class:"linkbtn", type:"button", "aria-expanded":String(open), onclick:() => {
      state.openWhy.has(key) ? state.openWhy.delete(key) : state.openWhy.add(key); why.classList.toggle("open"); toggle.setAttribute("aria-expanded", String(state.openWhy.has(key))); } }, "Why?");
  return el("div", { class:"item" },
    el("img", { src:r ? r.thumb : "", alt:`Receipt ${i.file}`, loading:"lazy" }),
    el("div", {}, el("div", {}, el("b", {}, i.vendor || i.file), el("span", { class:"muted" }, "  " + (i.receipt_date || "no date"))),
      el("div", { class:"row", style:"gap:6px;margin-top:3px" }, el("span", { class:"chip " + i.status }, STATUS[i.status]),
        el("span", { class:"chip cat" }, i.category.replace(/_/g, " ") + (i.category_source === "employee" ? " · you" : " · AI")), toggle)),
    el("div", { class:"amt" }, el("b", {}, left ? "—" : inr(i.eligible_inr)), el("small", {}, "bill " + inr(i.total_inr))),
    why);
}

/* ------------------------------ policy tab ------------------------------ */
async function loadPolicy() {
  const root = $("#tab-policy"); root.replaceChildren(el("div", { class:"card" }, "Reading policy documents… (the AI interprets them the first time)"));
  try { state.policy = await api("/api/policy"); renderPolicy(); }
  catch (e) { root.replaceChildren(el("div", { class:"banner err" }, e.message)); }
}
function renderPolicy(msg) {
  const root = $("#tab-policy"), p = state.policy;
  p.documents.sort((a, b) => b.text.length - a.text.length);  // main policy first
  const sel = el("select", { "aria-label":"Policy document", onchange:() => { ta.value = p.documents.find(d => d.name === sel.value).text; } }, p.documents.map(d => el("option", { value:d.name }, d.name)));
  const ta = el("textarea", { class:"doc", "aria-label":"Policy text" }); ta.value = p.documents[0].text;
  const status = el("div", { "aria-live":"polite", class:"muted", style:"margin-top:8px" }, msg || "");
  const save = el("button", { class:"primary", type:"button", onclick: async () => {
      save.disabled = true; status.textContent = "AI is re-reading the policy and re-checking your claim…";
      const before = state.snap.claim && state.snap.claim.eligible_inr;
      try { state.policy = await api(`/api/policy/${sel.value}`, { method:"PUT", headers:{ "Content-Type":"application/json" }, body:JSON.stringify({ text: ta.value }) });
        state.snap = await api(`/api/sessions/${state.sid}`); render();
        const after = state.snap.claim && state.snap.claim.eligible_inr;
        renderPolicy(before != null ? `Policy updated. Reimbursable total: ${inr(before)} → ${inr(after)}. No code was changed.` : "Policy updated."); }
      catch (e) { status.textContent = e.message; save.disabled = false; } } }, "Save & let the AI re-interpret");
  const reset = el("button", { class:"ghost", type:"button", onclick: async () => { state.policy = await post("/api/policy/reset"); state.snap = await api(`/api/sessions/${state.sid}`); render(); renderPolicy("Original policy restored."); } }, "Reset to original");
  const I = p.interpreted, doc = n => docCode(n);
  const rows = [
    ...I.limits.map(l => ["Limit", l.category, `${inr(l.amount)} ${l.unit.replace("_"," ")}${l.grades ? " · " + l.grades.join(",") : ""}`, l.over_limit_action.replace("_"," ") + (l.requires_approval ? " · prior approval" : ""), l]),
    ...I.exclusions.map(x => ["Excluded", x.category, "never reimbursable", x.reason, x]),
    ...I.age_rules.map(a => ["Rule", "all", `receipts ≤ ${a.max_age_days} days old`, "", a]),
  ];
  const table = el("table", {}, el("tr", {}, ["Type", "Category", "Constraint", "If exceeded", "Source clause"].map(h => el("th", {}, h))),
    rows.map(([t, c, k, a, it]) => el("tr", {}, el("td", {}, t), el("td", {}, c), el("td", {}, k), el("td", {}, a), el("td", { title:it.quote }, `${doc(it.document)}-${it.clause}`))));
  root.replaceChildren(
    el("section", { class:"card" }, el("h2", {}, "Policy documents (edit me)"), el("div", { class:"muted", style:"margin-bottom:8px" }, "Change a limit in the text, save, and watch the claim update. The AI reads the document; no rules are coded."),
      sel, ta, el("div", { class:"row", style:"margin-top:8px" }, save, reset), status),
    el("section", { class:"card" }, el("h2", {}, "What the AI extracted"), el("div", { class:"muted", style:"margin-bottom:8px" }, `${I.limits.length} limits · ${I.entitlements.length} entitlements · ${I.categories.length} categories. Every item is checked against a verbatim quote (hover a clause).`), table));
}

/* ------------------------------ finance tab ------------------------------ */
async function loadFinance() {
  const root = $("#tab-finance");
  try {
    const rows = await api("/api/finance/claims");
    root.replaceChildren(el("section", { class:"card" }, el("h2", {}, "Mock corporate reimbursement system — submitted claims"),
      rows.length ? el("table", {}, el("tr", {}, ["Reference", "Submitted", "Employee", "Grade", "On bills", "Reimbursable", "Status"].map(h => el("th", {}, h))),
        rows.map(r => el("tr", {}, el("td", {}, r.id), el("td", {}, r.created_at.replace("T", " ")), el("td", {}, r.employee_name), el("td", {}, r.grade), el("td", {}, inr(r.claimed_inr)), el("td", {}, inr(r.eligible_inr)), el("td", {}, r.status))))
        : el("div", { class:"muted" }, "No claims submitted yet.")));
  } catch (e) { root.replaceChildren(el("div", { class:"banner err" }, e.message)); }
}

/* ------------------------------ tabs ------------------------------ */
for (const b of document.querySelectorAll("nav button")) b.addEventListener("click", () => {
  document.querySelectorAll("nav button").forEach(x => x.setAttribute("aria-selected", String(x === b)));
  for (const t of ["claim", "policy", "finance"]) $("#tab-" + t).classList.toggle("hidden", t !== b.dataset.tab);
  if (b.dataset.tab === "policy") loadPolicy(); if (b.dataset.tab === "finance") loadFinance();
});
init().catch(e => { document.body.prepend(el("div", { class:"banner err" }, "Could not start: " + e.message)); });
</script>
</body>
</html>
```

