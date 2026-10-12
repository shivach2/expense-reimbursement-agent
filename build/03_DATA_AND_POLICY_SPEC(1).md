# 03 — Data and policy specification

All data is fictional ("Acme Corp"). The exact text of the policy documents and the employee file is in
`A4_SOURCE_config_data_docs.md` — create them verbatim; they are inputs the LLM interprets, so wording matters
(every limit sentence must contain its number so the grounding check can verify it).

## 1. Policy documents (`data/policies/*.md`)

Format rules the parser relies on:
* Title `# ...`, section headings `## N. Name`, clauses are lines starting with `N.M ` (e.g. `2.1 Hotel ...`),
  blank line between clauses. Clause numbers are what the LLM cites and what the grounding check looks up.
* Document short codes for references come from the file name: `travel_expense_policy.md` → **TEP**,
  `grade_entitlements.md` → **GE**. So a citation looks like `TEP-2.1`.

### What the LLM is expected to extract (use this to sanity-check your interpreter run)

`travel_expense_policy.md` (TEP)

| Clause | Text (abridged) | Expected constraint |
|---|---|---|
| 1.1 | receipts within 60 days, older not reimbursable | `age_rules`: 60 days |
| 1.2 | every claim must state business purpose | (no constraint; handled by the app's purpose question) |
| 1.3 | personal, medical, fines, penalties never reimbursable | `exclusions`: category like `personal_expenses` |
| 1.4 | limits in INR; other currencies converted first | (no constraint) |
| 2.1 | hotel up to INR 5,000 per night | `limits`: lodging 5000 `per_night` |
| 2.2 | excess borne by employee; partial reimbursement permitted | lodging `over_limit_action = partial` |
| 3.1 | meals up to INR 1,500 per receipt | meals 1500 `per_receipt` |
| 3.2 | above limit only with manager exception + recorded justification | meals `over_limit_action = needs_approval` |
| 4.1 | taxi/cab/parking/public transport up to INR 3,000 per day | local transport 3000 `per_day` (reject over) |
| 4.2 | fuel up to INR 2,500 per receipt | fuel 2500 `per_receipt` |
| 5.1 | client meals/entertainment up to INR 3,000 per receipt | client_entertainment 3000 `per_receipt` |
| 6.1 | training/conference up to INR 15,000 per receipt with prior written approval | training 15000 `per_receipt`, `requires_approval = true` |
| 7.1 | office supplies up to INR 1,000 per receipt | office_supplies 1000 `per_receipt` |

`grade_entitlements.md` (GE)

| Clause | Text (abridged) | Expected constraint |
|---|---|---|
| 1.1 | E1–E3 Executive, M1–M3 Manager, D1–D3 Director | (used to expand grade bands) |
| 2.1 | Executives may claim meals, local transport, fuel, communication, office supplies, training | entitlements, grades E1–E3 (the model may also list M/D grades for these categories) |
| 2.2 | Managers: everything Executives have, plus lodging and client entertainment | entitlements, grades M1–M3 |
| 2.3 | Directors: every Manager category | entitlements, grades D1–D3 |
| 3.1 | mobile/broadband up to INR 800 per month, Executive grades | communication 800 `per_month`, grades E1–E3 |
| 3.2 | up to INR 1,200 per month, Manager and Director grades | communication 1200 `per_month`, grades M1–M3, D1–D3 |

Typical result with Claude Sonnet 5.5: **9 limits, 8 entitlement items, 9 categories, 1 exclusion, 1 age rule**; category ids
`meals, local_transport, fuel, communication, office_supplies, training, lodging, client_entertainment, personal_expenses`.
The exact grouping of entitlement items and the id of the excluded category can differ between models
(e.g. `personal_medical`); the code and tests do not depend on them except where noted in `07`.

Expected eligibility: grade **M2** → `client_entertainment, communication, fuel, local_transport, lodging, meals, office_supplies, training`;
grade **E1** → `communication, fuel, local_transport, meals, office_supplies, training`.

## 2. Employee (`data/employees/emp_demo_m2.json`)

```json
{ "id": "EMP-0001", "name": "Asha Verma (synthetic)", "grade": "M2", "role": "Sales Manager", "base_city": "Pune" }
```

## 3. Synthetic receipts (`tools/generate_receipts.py` → `data/synthetic/receipts/`)

* 20 base receipts + 3 duplicates + 1 personal-expense receipt = **24 files** (mix of `.png` and `.pdf`).
* A receipt is drawn as a monospace till slip, 520 px wide: shop name (bold 28 pt), `Tel: 000-000-0000`, dashed rule,
  `Date: DD/MM/YYYY` (omitted when the date is missing), `Bill No: <1000 + crc32(vendor+date+total) % 9000>` (deterministic, so a
  re-photographed copy keeps the same bill number), item lines `name[:20]` left + price right, `Subtotal`, `Tax`, bold `TOTAL <Rs|$|EUR|S$>`,
  `Paid: CARD ****1234`, `Thank you!`.
* "Looks": `clean` (as drawn), `photo` (brown background, ±3–7° rotation, slight gray blend), `blurry` (photo + Gaussian blur 2.2),
  `crumpled` (±3–12° rotation, random light crease lines, blur 0.8). PDFs are the rendered image saved as PDF at 100 dpi.
* Totals are computed: `subtotal = Σ item prices`, `tax = subtotal × tax_rate`, `total = subtotal + tax` (rounded to 2 dp).
* Duplicates: `r21` is a byte-for-byte copy of `r01`; `r22` and `r23` are re-rendered "photo" versions of `r04` and `r02`
  (same content and bill number, different tilt).
* `ground_truth.json` = list of 24 objects: `file, vendor, date (ISO or null), total, tax, currency, category, scenario, duplicate_of`.
* Randomness: `random.seed(42)`; images are deterministic for a given Pillow/font setup. **PDF bytes contain timestamps, so PDF hashes differ on every
  regeneration** — this is why cached AI results are not portable between machines and Stage 7 re-warms the caches.
* Ground-truth categories use the policy category ids listed above (`personal_expenses` for the pharmacy bill). If your LLM chooses different ids for
  the same concepts, classification accuracy in `tools/run_pipeline.py` will look lower; compare by meaning.

### The 24 receipts (generated from the script's own specification — the table is exact)
| # | File | Vendor | Date | Line items (price) | Tax | Total | Cur | Look | Fmt | Truth category | Scenario |
|---|---|---|---|---|---|---|---|---|---|---|---|
| r01 | `r01_cafe.png` | Bluebird Cafe | 2026-09-14 | Filter Coffee 90; Sandwich 220; Muffin 100 | 5% | 430.5 | INR | clean | png | `meals` | clean |
| r02 | `r02_taxi.png` | Zippy Cabs | 2026-09-14 | Ride #4821 640 | 0% | 640 | INR | clean | png | `local_transport` | clean |
| r03 | `r03_hotel.pdf` | Lotus Grove Hotel | 2026-09-15 | Room 1 night 5800; Breakfast 600 | 12% | 7168 | INR | clean | pdf | `lodging` | clean |
| r04 | `r04_dinner_photo.png` | Saffron Table | 2026-09-15 | Thali 450; Lassi 120; Dessert 180 | 5% | 787.5 | INR | photo | png | `meals` | photo |
| r05 | `r05_stationery.png` | Paperwise Stores | 2026-09-16 | Notebook x2 240; Pens 120 | 18% | 424.8 | INR | clean | png | `office_supplies` | clean |
| r06 | `r06_blurry_lunch.png` | Green Leaf Eatery | 2026-09-16 | Bowl 380; Juice 140 | 5% | 546 | INR | blurry | png | `meals` | blurry |
| r07 | `r07_crumpled_fuel.png` | Highway Fuel Point | 2026-09-17 | Petrol 20L 2100 | 0% | 2100 | INR | crumpled | png | `fuel` | crumpled |
| r08 | `r08_foreign_usd.png` | Harbor Grill | 2026-09-18 | Burger 14.5; Fries 5; Soda 3 | 8% | 24.3 | USD | clean | png | `meals` | foreign_currency |
| r09 | `r09_foreign_sgd.pdf` | Marina Bay Taxi | 2026-09-18 | Airport transfer 32 | 9% | 34.88 | SGD | clean | pdf | `local_transport` | foreign_currency |
| r10 | `r10_missing_date.png` | Corner Stationers | (none printed) | Printer paper 150; Stapler 90 | 12% | 268.8 | INR | clean | png | `office_supplies` | missing_date |
| r11 | `r11_overlimit_meal.png` | Grand Terrace Dining | 2026-09-19 | Tasting menu x4 7200; Wine 3800 | 18% | 12980 | INR | photo | png | `meals` | over_limit |
| r12 | `r12_old_receipt.png` | Sunrise Bakery | 2026-03-02 | Cake 650 | 5% | 682.5 | INR | clean | png | `meals` | out_of_window |
| r13 | `r13_parking.png` | City Park Lot | 2026-09-20 | Parking 3h 120 | 0% | 120 | INR | clean | png | `local_transport` | clean |
| r14 | `r14_conf_fee.pdf` | NovaTech Summit | 2026-09-21 | Conference pass 9500 | 18% | 11210 | INR | clean | pdf | `training` | clean |
| r15 | `r15_train.png` | RailLink Express | 2026-09-22 | Ticket AC chair 1250 | 5% | 1312.5 | INR | photo | png | `local_transport` | clean |
| r16 | `r16_internet.pdf` | SwiftNet Broadband | 2026-09-01 | Monthly plan 999 | 18% | 1178.82 | INR | clean | pdf | `communication` | clean |
| r17 | `r17_taxi2.png` | Zippy Cabs | 2026-09-22 | Ride #5530 410 | 0% | 410 | INR | clean | png | `local_transport` | clean |
| r18 | `r18_lunch_client.png` | Olive & Oak | 2026-09-23 | Client lunch x3 2100; Drinks 540 | 5% | 2772 | INR | photo | png | `client_entertainment` | client_meal |
| r19 | `r19_hotel2.png` | Lotus Grove Hotel | 2026-09-23 | Room 1 night 5800 | 12% | 6496 | INR | clean | png | `lodging` | clean |
| r24 | `r24_pharmacy.png` | Corner Pharmacy | 2026-09-18 | Cough syrup 140; Vitamins 260 | 12% | 448 | INR | clean | png | `personal_expenses` | personal_expense |
| r20 | `r20_coffee2.png` | Bluebird Cafe | 2026-09-24 | Cappuccino 160 | 5% | 168 | INR | clean | png | `meals` | clean |
| r21 | `r21_dup_exact_cafe.png` | Bluebird Cafe | 2026-09-14 | (same as `r01_cafe.png`) | 5% | 430.5 | INR | identical bytes | png | `meals` | exact_duplicate of `r01_cafe.png` |
| r22 | `r22_dup_photo_dinner.png` | Saffron Table | 2026-09-15 | (same as `r04_dinner_photo.png`) | 5% | 787.5 | INR | photo, re-rendered | png | `meals` | near_duplicate of `r04_dinner_photo.png` |
| r23 | `r23_dup_taxi_photo.png` | Zippy Cabs | 2026-09-14 | (same as `r02_taxi.png`) | 0% | 640 | INR | photo, re-rendered | png | `local_transport` | near_duplicate of `r02_taxi.png` |

Notes: in the script's list `r24_pharmacy.png` sits before `r20`; in the folder, files simply sort by name. PDF receipts are exactly those with Fmt = pdf. Total = `subtotal × (1 + tax rate)` rounded to 2 decimals.
