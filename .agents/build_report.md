# Expense & Reimbursement Agent — Final Build Report

**Generated:** After completing Stages 0–9 (Stages 7, 8, and 10 require human action)  
**Track:** Track 1 — Expense & Reimbursement Agent  
**Project root:** `c:\Users\shiva\Projects\AI-Challenge-with-Kiro`

---

## 1. Build Summary

| Item | Result |
|---|---|
| Overall build status | ✅ **PASSED** (all automatable stages) |
| Pytest (no API key) | ✅ `125 passed, 8 skipped` |
| Ruff lint | ✅ `All checks passed!` |
| Ruff format | ✅ `42 files already formatted` |
| Stages requiring human action | Stages 7, 8, and 10 (API key, browser, video, GitHub) |

The codebase is fully built and all offline tests pass. The 8 skipped tests in `test_api.py` will become passing once the human completes Stage 7 (warm-up with a real LLM API key), at which point the expected total is **133 passed, 0 skipped**.

---

## 2. Stage-by-Stage Results

### Stage 0 — Scaffold and Environment

**Command:**
```powershell
py -m venv backend\venv
backend\venv\Scripts\pip.exe install --upgrade pip
backend\venv\Scripts\pip.exe install "pydantic-ai==2.54.0"
backend\venv\Scripts\pip.exe install -r backend\requirements-dev.txt
```

**Outcome:** ✅ PASSED  
All directories created. Virtual environment created at `backend/venv/`. All packages installed successfully on first attempt. Key packages confirmed: `pydantic-ai==2.54.0`, `fastapi==0.143.0`, `pymupdf==1.28.2`, `pillow==12.3.0`, `ruff==0.17.0`, `uvicorn==0.54.0`.

> `.env` file was NOT created — the human must supply their API key (see Section 7).

---

### Stage 1 — Generate Synthetic Receipts

**Command:**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
.\backend\venv\Scripts\python.exe tools\generate_receipts.py
```

**Actual Output:**
```
Wrote 24 receipts to C:\Users\shiva\Projects\AI-Challenge-with-Kiro\data\synthetic\receipts
```

**Outcome:** ✅ PASSED  
- 24 receipt files created (20 PNG + 4 PDF)
- `data/synthetic/ground_truth.json` has 24 entries
- 4 PDF files confirmed: `r03_hotel.pdf`, `r09_foreign_sgd.pdf`, `r14_conf_fee.pdf`, `r16_internet.pdf`

---

### Stage 2 — Extraction Core (23 tests)

**Command:**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
.\venv\Scripts\python.exe -m pytest -q tests/test_ingest.py tests/test_quality.py tests/test_extraction.py
```

**Actual Output:**
```
.......................                                                                         [100%]
23 passed in 26.33s
```

**Outcome:** ✅ PASSED

---

### Stage 3 — Duplicates and Grouping (cumulative 32)

**Command:**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
.\venv\Scripts\python.exe -m pytest -q tests/test_ingest.py tests/test_quality.py tests/test_extraction.py tests/test_duplicates.py tests/test_grouping.py
```

**Actual Output:**
```
................................                                                                [100%]
32 passed in 5.72s
```

**Outcome:** ✅ PASSED

---

### Stage 4 — Policy Layer (cumulative 58)

**Command:**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
.\venv\Scripts\python.exe -m pytest -q tests/test_ingest.py tests/test_quality.py tests/test_extraction.py tests/test_duplicates.py tests/test_grouping.py tests/test_policy_evaluator.py tests/test_policy_interpreter.py
```

**Actual Output (after fix):**
```
..........................................................                                      [100%]
58 passed in 3.16s
```

**Outcome:** ✅ PASSED (after one fix — see Section 6: Deviations)

**Fix applied:** `backend/pytest.ini` `pythonpath` changed from `. ` to `. tests` so that `test_policy_interpreter.py` can import `test_policy_evaluator` as a sibling module.

---

### Stage 5 — Classifier and Claim Builder (cumulative 76)

**Command:**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
.\venv\Scripts\python.exe -m pytest -q tests/test_ingest.py tests/test_quality.py tests/test_extraction.py tests/test_duplicates.py tests/test_grouping.py tests/test_policy_evaluator.py tests/test_policy_interpreter.py tests/test_classifier.py tests/test_claim.py
```

**Actual Output:**
```
............................................................................                    [100%]
76 passed in 2.86s
```

**Outcome:** ✅ PASSED

---

### Stage 6 — Full Test Suite (cumulative 125, 8 skipped)

**Command:**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
.\venv\Scripts\python.exe -m pytest -q
```

**Actual Output:**
```
ssssssss.......................................................................................[71%]
......................................                                                          [100%]
125 passed, 8 skipped in 5.40s
```

**Outcome:** ✅ PASSED  
The 8 skipped tests are in `tests/test_api.py` — they require warm AI caches from Stage 7. After Stage 7, the expected result is `133 passed, 0 skipped`.

---

### Stage 7 — Warm LLM Caches

**Status:** ⏭️ SKIPPED — requires the human's LLM API key.  
See Section 7b for exact commands.

---

### Stage 8 — Run App and Smoke Test

**Status:** ⏭️ SKIPPED — depends on Stage 7.  
See Section 7c for exact commands and the smoke-test checklist.

---

### Stage 9 — Quality Gates (Lint and Format)

**Command (lint):**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
.\backend\venv\Scripts\python.exe -m ruff check backend tools
```

**Actual Output:**
```
All checks passed!
```

**Command (format check):**
```powershell
.\backend\venv\Scripts\python.exe -m ruff format --check backend tools
```

**Actual Output:**
```
42 files already formatted
```

**Outcome:** ✅ PASSED

---

### Stage 10 — Documentation, Screenshots, Video, GitHub

**Status:** ⏭️ REQUIRES HUMAN ACTION  
All documentation files were created in Stage 0 (from appendix A5). The human must capture screenshots, record the demo video, and push to GitHub. See Section 7d for the full to-do list.

---

## 3. Final Pytest Summary

From Stage 6 (without API key / cold caches):
```
125 passed, 8 skipped in 5.40s
```

Expected after Stage 7 (with real API key and warm caches):
```
133 passed in 5.40s
```

---

## 4. Ruff Result

**Lint:**
```
All checks passed!
```

**Format check:**
```
42 files already formatted
```

---

## 5. Files Created — Summary

### From Stage 0 (A4 — configuration, data, CI): 13 files
`.gitignore`, `.env.example`, `pyproject.toml`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pytest.ini`, `DATA_POLICY.md`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.github/workflows/ci.yml`, `data/policies/travel_expense_policy.md`, `data/policies/grade_entitlements.md`, `data/employees/emp_demo_m2.json`

### From Stage 0 (A5 — documentation): 9 files
`README.md`, `docs/TECHNICAL_DESIGN.md`, `docs/SETUP_AND_DEPLOYMENT.md`, `docs/TEST_REPORT.md`, `docs/EVALUATION_MAPPING.md`, `docs/BUSINESS_IMPACT.md`, `docs/DEMO_VIDEO_GUIDE.md`, `docs/DEMO_SCRIPT.md`, `docs/SUBMISSION_CHECKLIST.md`

### From A1 — backend/app source: 21 files
`backend/app/__init__.py`, `config.py`, `models.py`, `currency.py`, `ingest.py`, `quality.py`, `extraction.py`, `duplicates.py`, `grouping.py`, `policy/__init__.py`, `policy/schema.py`, `policy/clauses.py`, `policy/interpreter.py`, `policy/evaluator.py`, `classifier.py`, `claim.py`, `pipeline.py`, `finance.py`, `state.py`, `chat.py`, `main.py`

### From A2 — backend tests: 18 files
`backend/pytest.ini`, `backend/tests/__init__.py`, `factories.py`, `test_ingest.py`, `test_quality.py`, `test_extraction.py`, `test_duplicates.py`, `test_grouping.py`, `test_policy_evaluator.py`, `test_policy_interpreter.py`, `test_classifier.py`, `test_claim.py`, `test_finance.py`, `test_state.py`, `test_chat_helpers.py`, `test_edge_cases.py`, `test_api_upload_and_errors.py`, `test_api.py`

### From A3 — tools and frontend: 5 files
`tools/generate_receipts.py`, `tools/extract_receipts.py`, `tools/run_pipeline.py`, `tools/make_deck.py`, `frontend/index.html`

### **Total: 66 files created**

---

## 6. Deviations from Appendix

Only one deviation occurred:

**`backend/pytest.ini` — `pythonpath` value**

| | Value |
|---|---|
| Appendix A2 original | `pythonpath = .` |
| Actual (after fix) | `pythonpath = . tests` |

**Reason:** `tests/test_policy_interpreter.py` imports `from test_policy_evaluator import GE, POLICY, TEP, make_policy` — a sibling test module import. This only works when `tests/` is on `sys.path`. The fix adds `tests` to `pythonpath`; no test logic or source logic was modified. The fix is minimal, necessary, and does not affect CI (CI runs `pytest` from `backend/` with the same `pytest.ini`).

No other deviations. All 66 source files were created verbatim from their respective appendix specifications.

---

## 7. What Only the Human Can Do

### a. Create the `.env` file

Copy `.env.example` to `.env` at the project root and fill in your credentials:

```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
copy .env.example .env
# Then open .env in your editor and fill in:
#   ANTHROPIC_API_KEY=sk-ant-...   (or GOOGLE_API_KEY=... for Gemini)
#   LLM_MODEL=anthropic:claude-3-5-sonnet-20241022   (or your chosen model)
```

The `.env` file is git-ignored and must never be committed. All other stages depend on this being done first.

---

### b. Stage 7 — Warm the LLM Caches and Unlock All 133 Tests

Run the warm-up pipeline (about 50 LLM calls, 1–3 minutes):

```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
backend\venv\Scripts\python.exe tools\run_pipeline.py --today 2026-10-12
```

**Expected pipeline output:**
- `policy: 2 documents -> 9 limits, 8 entitlements, 9 categories`
- A 24-row receipt table
- `claim state: needs_input` — `claimed INR 40,212 / eligible INR 23,053`
- About 5 questions
- Accuracy block: extraction 24/24, classification ~23/24

Then run the full test suite (now 133 tests should pass):

```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
.\venv\Scripts\python.exe -m pytest -q
```

**Expected:** `133 passed` with 0 skipped.

> **Note:** If using a free-tier model (about 20 requests/day cap), use `--limit 8` to stay within quota. In that case `test_api.py` may remain 8 skipped — note this in your submission.

---

### c. Stage 8 — Start the Server and Run the Smoke-Test Checklist

Start the server:

```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
$env:CLAIM_TODAY="2026-10-12"; .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Then open **http://localhost:8000** and walk through this checklist:

1. Header shows `Asha Verma (synthetic) · grade M2 · Sales Manager`.
2. Click **Try with the demo receipts** → progress bar → summary: `₹40,212.38 on the bills, ₹23,052.68 reimbursable, "Needs your input"`, ~5 questions, counts like `16 Needs info · 2 Needs review · 3 Not reimbursable · 3 Duplicate`.
3. Expand **Why?** on the Lotus Grove Hotel (15 Sep) bill: category reasoning, `"The bill is INR 7,168 but the limit is INR 5,000 per night x 1. Reimbursing INR 5,000; the excess INR 2,168 is not reimbursable."`, clause quotes `GE-2.2` and `TEP-2.1`.
4. Click chip **Why was my hotel reduced?** → a short answer citing `TEP-2.1`.
5. Open the **Policy** tab → change `INR 5,000 per night` to `INR 7,000 per night` → Save → status line: `Policy updated. Reimbursable total: ₹23,052.68 → ₹26,548.68. No code was changed.` → **Reset to original** restores it.
6. Answer all questions → **Ready to submit** → **Submit claim** → reference `RMB-<today YYYYMMDD>-0001`; Submit button becomes disabled.
7. Open the **Finance system** tab — claim is listed.
8. Visit http://localhost:8000/docs — FastAPI interactive docs render correctly.

---

### d. Stage 10 — Documentation, Screenshots, Video, GitHub

These items cannot be done by an automated agent:

**Screenshots** — After Stage 8, capture these 5 files into `docs/screenshots/` (browser width ~1280–1400 px):

| Filename | What to capture |
|---|---|
| `docs/screenshots/01_claim_and_chat.jpg` | Claim page after "Try with the demo receipts" and after asking "Why was my hotel reduced?" (chat answer visible beside the claim) |
| `docs/screenshots/02_explainable_decision.jpg` | Expanded **Why?** panel for Lotus Grove Hotel (15 Sep): category reasoning, policy decision, `GE-2.2` and `TEP-2.1` quotes |
| `docs/screenshots/03_policy_ai_interpreted.jpg` | Policy tab before editing (the "What the AI extracted" table) |
| `docs/screenshots/04_policy_changed_no_code.jpg` | Policy tab after changing `INR 5,000` to `INR 7,000` and saving (status line and updated lodging row visible) |
| `docs/screenshots/05_submitted.jpg` | Claim page after submit: chip `Submitted · RMB-...` and chat confirmation |

Then optionally build the PowerPoint deck:
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
.\backend\venv\Scripts\python.exe tools\make_deck.py
```

**Demo video** — Follow `docs/DEMO_VIDEO_GUIDE.md`:
- About 5 minutes; shows track selection, architecture diagram, uploading 24 bills, the claim, one explanation with a policy clause quote, the policy edit (5,000 → 7,000) changing the claim total, answering and submitting, the Finance tab, a terminal running `pytest` (133 passed, 100%) and `ruff check`, and the documentation on GitHub.
- Before recording, dry-run the policy edit once so the re-interpretation is cached (avoids a 10–20 s LLM wait on camera).
- Upload to YouTube as **Unlisted or Public** (never Private). Verify the link in an incognito window.

**README placeholders to fill in** (after recording and pushing):
- `YOUR_YOUTUBE_URL` — replace with your YouTube demo link
- `YOUR_HOSTED_URL` — replace with hosted URL (or remove if not hosted)
- `YOUR_NAME` — replace with your name

**GitHub submission:**
1. Create a **public** repository on your personal GitHub account.
2. From the project root:
   ```powershell
   cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
   git init
   git add .
   git commit -m "feat: complete Expense & Reimbursement Agent (Track 1)"
   git branch -M main
   git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO>.git
   git push -u origin main
   ```
3. Verify in an incognito window: README renders with Mermaid diagrams and images, no access prompt, GitHub Actions workflow is green.
4. Send the submission message per `docs/SUBMISSION_CHECKLIST.md`: repository link, design-document link, YouTube link, optional hosted link, track statement, synthetic-data statement. **Do not request permissions for any platform; make everything public/unlisted.**

---

## 8. Exact Commands to Start the App

**One-time setup (if not done already):**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
copy .env.example .env
# Edit .env: add ANTHROPIC_API_KEY and LLM_MODEL
```

**Warm the caches (Stage 7 — run once with API key set):**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
backend\venv\Scripts\python.exe tools\run_pipeline.py --today 2026-10-12
```

**Start the server (Stage 8):**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
$env:CLAIM_TODAY="2026-10-12"; .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Then open: **http://localhost:8000**

> If port 8000 is busy, use `--port 8001` and open that port instead.

**Run the full test suite (after Stage 7):**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
.\venv\Scripts\python.exe -m pytest -q
# Expected: 133 passed, 0 skipped
```

**Run coverage + lint (Stage 9 full check):**
```powershell
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
.\venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term-missing
# Expected: TOTAL ~1,380 statements, 0 missed, 100%

cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
.\backend\venv\Scripts\python.exe -m ruff check backend tools
# Expected: All checks passed!
```
