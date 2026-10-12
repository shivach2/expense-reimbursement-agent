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
