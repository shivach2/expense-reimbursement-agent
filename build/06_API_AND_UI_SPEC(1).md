# 06 — REST API and UI specification

Base URL: `http://localhost:8000`. JSON everywhere except uploads (multipart) and thumbnails (JPEG).
Errors use FastAPI's standard shape `{"detail": "<message>"}`.

## 1. Endpoints

| Method + path | Body | Success | Errors |
|---|---|---|---|
| `POST /api/sessions` | – | 200 snapshot of a new empty session | – |
| `GET /api/sessions/{sid}` | – | 200 snapshot | 404 `Unknown session` |
| `POST /api/sessions/{sid}/receipts` | multipart field `files` (one or many) | **202** snapshot (`status:"processing"`); work continues in a background task | 400 `<name>: only images and PDFs are supported` / `At most 40 files at a time`; 409 `Still processing the previous upload` / `This claim was already submitted; start a new one`; 413 `<name>: larger than 10 MB`; 404 |
| `POST /api/sessions/{sid}/demo` | – | 202 snapshot; loads the 24 bundled synthetic receipts and processes them **with the extraction cache enabled** | 409 `Still processing`; 404 |
| `GET /api/sessions/{sid}/thumb/{name}` | – | 200 `image/jpeg` (first page, max side 500 px, `Cache-Control: max-age=3600`) | 404 `Unknown file` (also for path-traversal attempts); 415 |
| `POST /api/sessions/{sid}/answers` | `{"kind": str, "target": str, "value": any}` | 200 snapshot after rebuilding the claim | 422 (invalid kind/target/value/date/category); 409 already submitted |
| `POST /api/sessions/{sid}/chat` | `{"message": str (1..2000)}` | 200 `{"reply": str, "session": snapshot}` | 409 `Upload receipts first`; 503 (`UserError`, e.g. missing API key); 502 (other AI service failure) |
| `POST /api/sessions/{sid}/submit` | – | 200 `{"submission": {"id","created_at","eligible_inr"}, "session": snapshot}` | 409 `Already submitted as RMB-...` / `Nothing to submit` / `Claim is needs_input; it must be ready before it can be submitted` |
| `GET /api/policy` | – | 200 `{"documents":[{"name","text"}], "interpreted":{categories, entitlements, limits, exclusions, age_rules}}` | 502/503 |
| `PUT /api/policy/{name}` | `{"text": str (10..50000)}` | 200 same shape as `GET /api/policy`; the document is rewritten in the **runtime copy**, re-interpreted, and **every session's claim is recomputed** | 404 `Unknown policy document`; on interpretation failure the previous text is restored and 502/503 returned |
| `POST /api/policy/reset` | – | 200 policy view; restores the original documents | 502/503 |
| `GET /api/finance/claims` | – | 200 list `[{id, created_at, employee_id, employee_name, grade, claimed_inr, eligible_inr, status}]` newest first | – |
| `GET /api/finance/claims/{id}` | – | 200 row + `payload` (the full claim JSON) | 404 `Unknown claim` |
| `GET /api/health` | – | `{"ok": true, "model": "<LLM_MODEL>"}` | – |
| `GET /` | – | the single-page UI (`frontend/index.html`) | – |
| `GET /docs`, `GET /openapi.json` | – | FastAPI interactive API documentation (registered before the static mount, so it is not shadowed) | – |

`answers.kind` values: `purpose_group` (target = group id like `g-2026-09-14`), `purpose_item`, `justification`, `category` (value must be a
policy category id), `vendor`, `date` (ISO `YYYY-MM-DD`), `amount` (number), `currency` (3 letters), `confirm`, `not_duplicate`.
All receipt-targeted kinds take the receipt **file name** as `target`.

Typical client flow: create session → `demo` or `receipts` → poll `GET /api/sessions/{sid}` every ~700 ms until `status` is `ready` or `error`
→ answer questions → `submit`.

## 2. Snapshot JSON shape

```
{ "id": "<12 hex>", "status": "idle|processing|ready|error", "error": null|"<Type>: <message>",
  "progress": {"done": int, "total": int}, "submitted_ref": null|"RMB-YYYYMMDD-NNNN",
  "employee": {id,name,grade,role,base_city},
  "claim": null | { "state": "ready|needs_input|blocked", "employee": {...},
       "items": [ClaimItem...], "groups": [{id,title,start,end,files[],eligible_inr}],
       "questions": [{id,kind,target,text,fields[],options[]}],
       "eligible_by_category": {cat: amount}, "claimed_inr": n, "eligible_inr": n, "counts": {status: n} },
  "receipts": { "<file>": { "extracted": ExtractedReceipt-without-sha, "classification": Classification|null,
                            "thumb": "/api/sessions/<sid>/thumb/<file>" } } }
```
A background-processing failure leaves `status:"error"` with `error` set: `The AI model is not configured: ...` when the key is missing (`UserError`), otherwise `<ExceptionType>: <message>`; the previous claim stays intact. Real captured examples are appended at the end of this file.

## 3. UI specification (`frontend/index.html`)

Single file; `<style>` + `<script>`; no external assets. Light theme; system font; blue accent `#1d4ed8`.

**Header**: title "Expense & Reimbursement Agent"; employee line `"<name> · grade <g> · <role>"`; tabs (ARIA `tablist`): **Claim**, **Policy (AI-interpreted)**, **Finance system**.

**Claim tab** — two columns (chat 300–380 px | claim), single column under 900 px:
* *Chat panel* (sticky, full height): greeting message *"Hi! Drop in your bills (photos or PDFs) and I'll build the claim, check it against the policy, and ask only what I can't work out myself."*;
  quick chips: "What's still missing?", "Why was my hotel reduced?", "What's the meal limit?", "Which bills were left out?"; text input + Send. Bot replies render `**bold**` as `<b>`; everything else is text.
  Chat before any claim exists replies locally: "Upload some receipts first and then I can help with the claim."
  When processing finishes the bot posts: `Done. N receipts read. D duplicate(s) and I not reimbursable were left out. ` + either `I need Q thing(s) from you — they're listed on the right.` or `Nothing else needed — you can submit.`
* *Upload card*: drag-and-drop zone (also click/Enter/Space to open the file picker; accepts images and PDFs, multiple) and a button
  **"Try with the demo receipts (24 synthetic bills)"** (disabled while processing or after submit). After submit the zone title becomes "Claim submitted".
* *Progress card* while processing: `Reading and checking receipts… done/total` and a progress bar.
* *Summary card*: state chip (`Ready to submit` / `Needs your input` / `Nothing claimable`, or `Submitted · <ref>`), three KPIs (**on the bills** = `claimed_inr`, **reimbursable under policy** = `eligible_inr`,
  **open question(s)**), status counts line (`16 Needs info · 2 Needs review · 3 Not reimbursable · 3 Duplicate`), and the **Submit claim** button, enabled only when state is `ready`, not yet submitted and not processing.
* *Questions card* ("I need N thing(s) from you") — one block per question with the question text and widgets by kind:
  `purpose` → text input + Save (kind `purpose_group`, target = group id); `justify` → text input (kind `justification`); `field` → one input per missing field
  (`date` date picker, `vendor` text, `amount` number, `currency` text); `clarify` → select of `options` (kind `category`); `confirm` → button "Yes, that's correct". Empty inputs are ignored.
* *Claim card* ("Your claim"): receipts grouped under group headers (`title` + `<eligible> reimbursable`); then "Needs a date before it can be grouped" for ungrouped non-excluded items; then "Left out of the claim" (duplicates, ineligible; slightly faded).
  Each item row: 56×72 thumbnail (`/api/sessions/<sid>/thumb/<file>`, lazy), **vendor** + date, a status chip (`Complete`, `Needs info`, `Needs review`, `Duplicate`, `Not reimbursable`), a category chip
  (`<category with _ → space> · AI` or `· you`), a **Why?** toggle (`aria-expanded`), and on the right the eligible amount (or `—` for left-out items) with `bill ₹<claimed>` below.
  The *Why?* panel shows: "Why this category: <reasoning>", "Policy decision: <explanation>", one blockquote per cite `<ref> (<document>): “<quote>”`, "Needed: ...", extra reasons as bullets, and
  "Read from bill: vendor, date, total currency · confidence vendor x, date y, total z". Open/closed state survives re-renders.
* Currency formatting: `₹` + `toLocaleString("en-IN", {maximumFractionDigits: 2})`; `—` for null.

**Policy tab** — two cards: left "Policy documents (edit me)" (document `<select>`, the longest document selected first, a monospace `<textarea>`, button **"Save & let the AI re-interpret"**, button **"Reset to original"**, an `aria-live` status line);
right "What the AI extracted" (counts line + table with columns Type, Category, Constraint, If exceeded, Source clause; the clause cell shows `<DOCCODE>-<clause>` with the verbatim quote as its `title` tooltip).
After saving, the status line reads `Policy updated. Reimbursable total: ₹23,052.68 → ₹26,548.68. No code was changed.` (when a claim exists) and the claim tab re-renders with the new numbers.

**Finance tab** — table of submitted claims (Reference, Submitted, Employee, Grade, On bills, Reimbursable, Status) or "No claims submitted yet."

**Accessibility/security**: labelled inputs, focus outlines, keyboard-operable drop zone, `aria-live` regions for progress/chat/status; DOM built by an `el(tag, attrs, ...children)` helper that never uses `innerHTML`
(it throws if an `html` attribute is passed); errors appear as a dismissing banner at the top of the claim column.

## 4. Captured real API examples (generated from a working build)

All examples below were captured from a finished build running offline from cached Claude results (`today = 2026-10-12`). Your numbers for deterministic parts must match; LLM wording may differ.

### New session

`POST /api/sessions` → **200**

```json
{
  "id": "6bf13e5e10e5",
  "status": "idle",
  "error": null,
  "progress": {
    "done": 0,
    "total": 0
  },
  "submitted_ref": null,
  "employee": {
    "id": "EMP-0001",
    "name": "Asha Verma (synthetic)",
    "grade": "M2",
    "role": "Sales Manager",
    "base_city": "Pune"
  },
  "claim": null,
  "receipts": {}
}
```

### Start the demo load (background processing)

`POST /api/sessions/{sid}/demo` → **202** — poll GET /api/sessions/{sid} until status is ready

```json
{
  "id": "6bf13e5e10e5",
  "status": "processing",
  "error": null,
  "progress": {
    "done": 0,
    "total": 0
  },
  "submitted_ref": null,
  "claim": null,
  "receipts": {}
}
```

### Claim summary after processing (items/receipts abridged below)

`GET /api/sessions/{sid}` → **200**

```json
{
  "id": "6bf13e5e10e5",
  "status": "ready",
  "progress": {
    "done": 24,
    "total": 24
  },
  "claim": {
    "state": "needs_input",
    "claimed_inr": 40212.38,
    "eligible_inr": 23052.68,
    "counts": {
      "missing_info": 16,
      "questionable": 2,
      "ineligible": 3,
      "duplicate": 3
    },
    "eligible_by_category": {
      "meals": 1932.0,
      "local_transport": 4645.06,
      "lodging": 10000.0,
      "office_supplies": 424.8,
      "fuel": 2100.0,
      "training": 0.0,
      "communication": 1178.82,
      "client_entertainment": 2772.0
    },
    "groups": [
      {
        "id": "g-2026-09-01",
        "title": "Expenses on 01 Sep 2026",
        "start": "2026-09-01",
        "end": "2026-09-01",
        "files": [
          "r16_internet.pdf"
        ],
        "eligible_inr": 1178.82
      },
      {
        "id": "g-2026-09-14",
        "title": "Expenses 14 Sep – 24 Sep 2026",
        "start": "2026-09-14",
        "end": "2026-09-24",
        "files": [
          "r01_cafe.png",
          "r02_taxi.png",
          "r03_hotel.pdf",
          "r04_dinner_photo.png",
          "r05_stationery.png",
          "r06_blurry_lunch.png",
          "r07_crumpled_fuel.png",
          "r08_foreign_usd.png",
          "r09_foreign_sgd.pdf",
          "r13_parking.png",
          "r14_conf_fee.pdf",
          "r15_train.png",
          "r17_taxi2.png",
          "r18_lunch_client.png",
          "r19_hotel2.png",
          "r20_coffee2.png"
        ],
        "eligible_inr": 21873.86
      }
    ],
    "questions": [
      {
        "id": "justify:r08_foreign_usd.png",
        "kind": "justify",
        "target": "r08_foreign_usd.png",
        "text": "HARBOR GRILL: The bill is INR 2,016.90, above the INR 1,500 per receipt limit. It can be reimbursed only as an approved exception. Policy TEP-3.1: \"Meals during business travel are reimbursable up to INR 1,500 per receipt.\" Please provide manager-approved justification.",
        "fields": [],
        "options": []
      },
      {
        "id": "field:r10_missing_date.png",
        "kind": "field",
        "target": "r10_missing_date.png",
        "text": "CORNER STATIONERS: please provide the date.",
        "fields": [
          "date"
        ],
        "options": []
      },
      {
        "id": "justify:r14_conf_fee.pdf",
        "kind": "justify",
        "target": "r14_conf_fee.pdf",
        "text": "NOVATECH SUMMIT: Training needs prior approval before it can be reimbursed. Policy TEP-6.1: \"Training courses and conference fees are reimbursable up to INR 15,000 per receipt, and require prior written approval from the employee's manager.\" Please provide approval reference or justification.",
        "fields": [],
        "options": []
      },
      {
        "id": "purpose:g-2026-09-14",
        "kind": "purpose",
        "target": "g-2026-09-14",
        "text": "What was the business purpose of these 16 receipt(s)? (Expenses 14 Sep – 24 Sep 2026)",
        "fields": [],
        "options": []
      },
      {
        "id": "purpose:g-2026-09-01",
        "kind": "purpose",
        "target": "g-2026-09-01",
        "text": "What was the business purpose of these 1 receipt(s)? (Expenses on 01 Sep 2026)",
        "fields": [],
        "options": []
      }
    ],
    "items": "[24 ClaimItem objects]"
  }
}
```

### One ClaimItem (hotel, partial reimbursement with citations)

`snapshot.claim.items[?]` → **-**

```json
{
  "file": "r03_hotel.pdf",
  "vendor": "LOTUS GROVE HOTEL",
  "receipt_date": "2026-09-15",
  "total": 7168.0,
  "currency": "INR",
  "total_inr": 7168.0,
  "category": "lodging",
  "category_source": "ai",
  "category_reasoning": "The bill is from a hotel for one night's room stay plus breakfast, which is part of the hotel folio. The total above the line items (7168 vs 6400) is normal tax, so this fits lodging.",
  "status": "missing_info",
  "reasons": [
    "The bill is INR 7,168 but the limit is INR 5,000 per night x 1. Reimbursing INR 5,000; the excess INR 2,168 is not reimbursable. Policy TEP-2.1: \"Hotel accommodation is reimbursable up to INR 5,000 per night.\"",
    "Business purpose needed"
  ],
  "decision": {
    "outcome": "partial",
    "category": "lodging",
    "claimed_inr": 7168.0,
    "eligible_inr": 5000.0,
    "explanation": "The bill is INR 7,168 but the limit is INR 5,000 per night x 1. Reimbursing INR 5,000; the excess INR 2,168 is not reimbursable. Policy TEP-2.1: \"Hotel accommodation is reimbursable up to INR 5,000 per night.\"",
    "cites": [
      {
        "ref": "GE-2.2",
        "document": "grade_entitlements.md",
        "quote": "Manager grades are eligible to claim everything available to Executive grades, and additionally lodging and client entertainment."
      },
      {
        "ref": "TEP-2.1",
        "document": "travel_expense_policy.md",
        "quote": "Hotel accommodation is reimbursable up to INR 5,000 per night."
      }
    ],
    "needs": []
  },
  "eligible_inr": 5000.0,
  "duplicate_of": null,
  "group_id": "g-2026-09-14"
}
```

### One receipts entry (USD receipt: extraction + classification + thumb)

`snapshot.receipts['r08_foreign_usd.png']` → **-**

```json
{
  "extracted": {
    "source_file": "r08_foreign_usd.png",
    "model": "anthropic:claude-sonnet-5-5",
    "receipt": {
      "readable": true,
      "vendor": "HARBOR GRILL",
      "receipt_date": "2026-09-18",
      "total": 24.3,
      "tax": 1.8,
      "currency": "USD",
      "category": "restaurant meal",
      "nights": null,
      "line_items": [
        {
          "description": "Burger",
          "amount": 14.5
        },
        {
          "description": "Fries",
          "amount": 5.0
        },
        {
          "description": "Soda",
          "amount": 3.0
        }
      ],
      "receipt_number": "9415",
      "payment_method": "CARD",
      "confidence": {
        "vendor": 0.97,
        "date": 0.95,
        "total": 0.97
      },
      "notes": "Currency inferred from the '$' symbol next to TOTAL; the specific dollar currency (USD vs others) is not stated. Receipt date 18/09/2026 is in the future relative to typical processing, so verify."
    },
    "total_inr": 2016.9,
    "needs_review": false,
    "review_reasons": [],
    "error": null
  },
  "classification": {
    "category": "meals",
    "reasoning": "The bill is from a restaurant (Harbor Grill) for a burger, fries and a soda, which is a standard meal expense. The total is slightly above the line items, which is normal tax.",
    "confidence": 0.95,
    "needs_clarification": false,
    "clarification_question": null
  },
  "thumb": "/api/sessions/6bf13e5e10e5/thumb/r08_foreign_usd.png"
}
```

### Submit too early

`POST /api/sessions/{sid}/submit` → **409**

```json
{
  "detail": "Claim is needs_input; it must be ready before it can be submitted"
}
```

### Answer a justification question

`POST /api/sessions/{sid}/answers` → **200** — response is the full snapshot; abridged here

```json
{
  "questions_before": 5,
  "questions_after": 4,
  "r08_status": "missing_info",
  "eligible_inr": 25069.58
}
```

### Invalid answer

`POST /api/sessions/{sid}/answers` → **422**

```json
{
  "detail": "'yachts' is not a policy category"
}
```

### Bad upload

`POST /api/sessions/{sid}/receipts` → **400**

```json
{
  "detail": "notes.txt: only images and PDFs are supported"
}
```

### Unknown session

`POST /api/sessions/nope/demo` → **404**

```json
{
  "detail": "Unknown session"
}
```

### Submit a ready claim

`POST /api/sessions/{sid}/submit` → **200**

```json
{
  "submission": {
    "id": "RMB-20261012-0001",
    "created_at": "2026-10-12T16:14:10",
    "eligible_inr": 36548.38
  },
  "session.submitted_ref": "RMB-20261012-0001",
  "session.claim.state": "ready"
}
```

### Finance list

`GET /api/finance/claims` → **200**

```json
[
  {
    "id": "RMB-20261012-0001",
    "created_at": "2026-10-12T16:14:10",
    "employee_id": "EMP-0001",
    "employee_name": "Asha Verma (synthetic)",
    "grade": "M2",
    "claimed_inr": 40212.38,
    "eligible_inr": 36548.38,
    "status": "submitted"
  }
]
```

### Finance claim detail

`GET /api/finance/claims/{id}` → **200**

```json
{
  "id": "RMB-20261012-0001",
  "created_at": "2026-10-12T16:14:10",
  "employee_id": "EMP-0001",
  "employee_name": "Asha Verma (synthetic)",
  "grade": "M2",
  "claimed_inr": 40212.38,
  "eligible_inr": 36548.38,
  "status": "submitted",
  "payload": "<full claim JSON: state=ready, 24 items>"
}
```

### Second submit

`POST /api/sessions/{sid}/submit` → **409**

```json
{
  "detail": "Already submitted as RMB-20261012-0001"
}
```

### Chat before receipts

`POST /api/sessions/{sid}/chat` → **409**

```json
{
  "detail": "Upload receipts first"
}
```

### Policy view (abridged)

`GET /api/policy` → **200**

```json
{
  "documents": [
    {
      "name": "grade_entitlements.md",
      "text": "# Acme Corp Grade Entitlements Matrix\n\nFictional company. Synthetic document wri..."
    },
    {
      "name": "travel_expense_policy.md",
      "text": "# Acme Corp Travel and Expense Policy\n\nFictional company. Synthetic document wri..."
    }
  ],
  "interpreted": {
    "categories": [
      {
        "id": "meals",
        "label": "Meals",
        "description": "Meal expenses"
      },
      {
        "id": "local_transport",
        "label": "Local transport",
        "description": "Local transport expenses"
      }
    ],
    "limits (first 2 of 9)": [
      {
        "clause": "3.1",
        "quote": "Mobile and broadband bills are reimbursable up to INR 800 per month for Executive grades.",
        "document": "grade_entitlements.md",
        "category": "communication",
        "amount": 800.0,
        "currency": "INR",
        "unit": "per_month",
        "grades": [
          "E1",
          "E2",
          "E3"
        ],
        "over_limit_action": "partial",
        "requires_approval": false
      },
      {
        "clause": "3.2",
        "quote": "Mobile and broadband bills are reimbursable up to INR 1,200 per month for Manager and Director grades.",
        "document": "grade_entitlements.md",
        "category": "communication",
        "amount": 1200.0,
        "currency": "INR",
        "unit": "per_month",
        "grades": [
          "M1",
          "M2",
          "M3",
          "D1",
          "D2",
          "D3"
        ],
        "over_limit_action": "partial",
        "requires_approval": false
      }
    ],
    "exclusions": [
      {
        "clause": "1.3",
        "quote": "Personal expenses, medical expenses, fines and penalties are not reimbursable under any circumstances.",
        "document": "travel_expense_policy.md",
        "category": "personal_expenses",
        "reason": "Personal expenses, medical expenses, fines and penalties are not reimbursable under any circumstances."
      }
    ],
    "age_rules": [
      {
        "clause": "1.1",
        "quote": "Expense receipts must be submitted within 60 days of the date of the expense.",
        "document": "travel_expense_policy.md",
        "max_age_days": 60
      }
    ]
  }
}
```

### Health

`GET /api/health` → **200**

```json
{
  "ok": true,
  "model": "anthropic:claude-sonnet-5-5"
}
```
