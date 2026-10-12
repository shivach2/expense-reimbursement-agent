# 08 — Build stages, run instructions and troubleshooting

Run commands from the **project root** unless stated. `PY` means the venv's Python
(`.venv/bin/python` on macOS/Linux, `.venv\Scripts\python.exe` on Windows). After each stage, paste the real output.

## Stage 0 — Scaffold and environment

Create (from the appendix, verbatim): `.gitignore`, `.env.example`, `DATA_POLICY.md`, `pyproject.toml`, `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pytest.ini`.
```bash
python3 -m venv .venv            # Windows: py -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install "pydantic-ai==2.54.0"
pip install -r backend/requirements-dev.txt          # includes backend/requirements.txt, pytest-cov, ruff, python-pptx
pip list | grep -iE "pydantic|fastapi|pymupdf|pillow|uvicorn|multipart|dotenv|httpx2|pytest|ruff"   # Windows: pip list | findstr /i "pydantic fastapi ..."
mkdir -p backend/app/policy backend/tests frontend tools data/policies data/employees docs .github/workflows
```
Create `.env` from `.env.example` and fill in your key + `LLM_MODEL` (the human supplies the key; never paste it into chat). `git init` is optional.
**Expect:** versions as in `02_...` (pydantic-ai 2.54.x, fastapi 0.14x, pymupdf 1.2x, pillow >= 10.1, ruff 0.17.x).

## Stage 1 — Synthetic data
Files: `tools/generate_receipts.py`.
```bash
PY tools/generate_receipts.py
```
**Expect:** `Wrote 24 receipts to .../data/synthetic/receipts`; 24 files there (`r01_cafe.png` … `r24_pharmacy.png`; exactly 4 are `.pdf`: `r03_hotel.pdf`, `r09_foreign_sgd.pdf`, `r14_conf_fee.pdf`, `r16_internet.pdf`; the rest are `.png`);
`data/synthetic/ground_truth.json` has 24 entries; category counts `meals 9, local_transport 6, lodging 2, office_supplies 2, fuel 1, training 1, communication 1, client_entertainment 1, personal_expenses 1`.
Open `r07_crumpled_fuel.png` — a tilted till slip with crease lines; `r22_dup_photo_dinner.png` shows the same bill number as `r04`.

## Stage 2 — Extraction core
Files: `backend/app/__init__.py` (empty), `config.py`, `currency.py`, `models.py`, `ingest.py`, `quality.py`, `extraction.py`; tests `test_ingest.py`, `test_quality.py`, `test_extraction.py`.
```bash
cd backend && PY -m pytest -q tests/test_ingest.py tests/test_quality.py tests/test_extraction.py
```
**Expect:** `23 passed`. (Optional live check once the key is set, from the root: `PY tools/extract_receipts.py --limit 3` → three `[ok]` lines and `3/3 (100%)`; file `tools/extract_receipts.py`.)

## Stage 3 — Duplicates and grouping
Files: `duplicates.py`, `grouping.py`; tests `test_duplicates.py`, `test_grouping.py`. **Expect** cumulative `32 passed`.

## Stage 4 — Policy layer
Files: `data/policies/travel_expense_policy.md`, `data/policies/grade_entitlements.md`, `data/employees/emp_demo_m2.json`, `backend/app/policy/{__init__,schema,clauses,interpreter,evaluator}.py`;
tests `test_policy_evaluator.py`, `test_policy_interpreter.py`. **Expect** cumulative `58 passed`. Optional live check (real LLM, ~20 s, creates the policy cache):
```python
PY - <<'E'
import asyncio, sys; sys.path.insert(0, "backend")
from app.config import get_settings
from app.policy.interpreter import load_policy_set
p = asyncio.run(load_policy_set(get_settings().policy_dir, settings=get_settings()))
print(len(p.limits), len(p.entitlements), sorted(p.category_ids()))
E
```
**Expect** about `9 8 [...9 category ids...]` and the hotel limit `5000 per_night`.

## Stage 5 — Classifier and claim builder
Files: `classifier.py`, `claim.py`; tests `test_classifier.py`, `test_claim.py` (needs `data/synthetic/ground_truth.json` from Stage 1). **Expect** cumulative `76 passed`.

## Stage 6 — Pipeline, finance, app, UI, CLI tools and the remaining tests
Files: `pipeline.py`, `finance.py`, `state.py`, `chat.py`, `main.py`, `frontend/index.html`, `tools/run_pipeline.py`, `tools/extract_receipts.py`, `tools/make_deck.py`;
tests `test_finance.py`, `factories.py` (shared helper, not a test), `test_state.py`, `test_chat_helpers.py`, `test_edge_cases.py`, `test_api_upload_and_errors.py`, `test_api.py`.
```bash
cd backend && PY -m pytest -q
```
**Expect:** `125 passed, 8 skipped` — the 8 skipped are `tests/test_api.py` (they need the warm AI caches; the skip message says so). Also `PY -c "import sys; sys.path.insert(0,'backend'); import app.main"` imports cleanly.

## Stage 7 — Warm the caches with the real LLM, then the full suite
```bash
PYDANTIC_AI_NO_BANNER=1 PY tools/run_pipeline.py --today 2026-10-12      # ~50 LLM calls, 1–3 minutes
cd backend && PY -m pytest -q
```
**Expect:** the pipeline prints `policy: 2 documents -> 9 limits, 8 entitlements, 9 categories`, the 24-row table, `claim state: needs_input` with about `claimed INR 40,212 / eligible INR 23,053`,
**about 5 questions**, and an accuracy block (extraction 24/24 each field with a strong model; classification about 23/24). It writes `data/eval/<model>.json` and the three cache folders.
Then **`133 passed`** with no skips. (The policy-edit API test makes one live call the first time, about 10–20 s, then it is cached.)
If a free-tier model is used see the quota notes below; `--limit 8` keeps a run inside a 20-request daily cap (then the API tests may stay skipped; say so).

## Stage 8 — Run the app and smoke-test
```bash
cd backend
CLAIM_TODAY=2026-10-12 PY -m uvicorn app.main:app --port 8000        # Windows PowerShell: $env:CLAIM_TODAY="2026-10-12"; ...
```
Open http://localhost:8000 and walk the checklist:
1. Header shows `Asha Verma (synthetic) · grade M2 · Sales Manager`.
2. **Try with the demo receipts** → progress bar → summary: ₹40,212.38 on the bills, ₹23,052.68 reimbursable, "Needs your input", ~5 questions, counts like `16 Needs info · 2 Needs review · 3 Not reimbursable · 3 Duplicate`.
3. Expand **Why?** on the Lotus Grove Hotel (15 Sep) bill: category reasoning, "The bill is INR 7,168 but the limit is INR 5,000 per night x 1. Reimbursing INR 5,000; the excess INR 2,168 is not reimbursable.", clause quotes `GE-2.2` and `TEP-2.1`.
4. Chip **Why was my hotel reduced?** → a short answer citing `TEP-2.1` (needs the LLM key).
5. **Policy** tab → change `INR 5,000 per night` to `INR 7,000 per night` → Save → `Policy updated. Reimbursable total: ₹23,052.68 → ₹26,548.68. No code was changed.`; **Reset to original** restores it.
6. Answer the questions → **Ready to submit** → **Submit claim** → reference `RMB-<today YYYYMMDD>-0001`; Submit disabled.
7. **Finance system** tab lists the claim. `http://localhost:8000/docs` shows the FastAPI interactive docs.

## Stage 9 — Quality gates (coverage, lint, format, CI simulation)
```bash
cd backend
ANTHROPIC_API_KEY=dummy PY -m pytest -q --cov=app --cov-report=term-missing     # expect: 133 passed; TOTAL ~1,380 statements, 0 missed, 100%
cd .. && ruff check backend tools                                                # expect: All checks passed!
ruff format --check backend tools                                               # expect: files already formatted (run `ruff format backend tools` if the agent touched formatting)
```
CI simulation on a clean copy (no `.env`, no `.venv`): copy the project to a temp folder excluding `.venv`, `.git`, `.env`, `backend/runtime`, `rebuild_prompt`, then there run
`ruff check backend tools` and, from `backend/`, `ANTHROPIC_API_KEY=ci-dummy-key LLM_MODEL=<your model> PY -m pytest -q --cov=app --cov-report=term --cov-fail-under=95` → **must pass**
(this mirrors `.github/workflows/ci.yml`; it needs the warm caches that Stage 7 created, and they must be committed to git in the real repository).
Cold-cache behaviour: `LLM_MODEL=anthropic:never-warmed-model PY -m pytest -q tests/test_api.py` → `8 skipped` (not failed).

## Stage 10 — Documentation, diagrams, screenshots, Docker, submission preparation
Files (from appendix `A5`, plus `A4` for Docker/CI): `README.md`, `docs/TECHNICAL_DESIGN.md`, `docs/SETUP_AND_DEPLOYMENT.md`, `docs/TEST_REPORT.md`, `docs/EVALUATION_MAPPING.md`, `docs/BUSINESS_IMPACT.md`,
`docs/DEMO_VIDEO_GUIDE.md`, `docs/DEMO_SCRIPT.md`, `docs/SUBMISSION_CHECKLIST.md`, `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `.github/workflows/ci.yml`.
Then follow **`09_DOCUMENTATION_VIDEO_AND_SUBMISSION.md`**: verify the 8 Mermaid diagrams parse, correct any document number that differs from your measured numbers, check links, capture the five screenshots
(or list them for the human), optionally build the deck (`PY tools/make_deck.py`), optionally build/run the Docker image, run the confidentiality greps, and produce the human to-do list
(video, GitHub, placeholders).

---

## Troubleshooting table

| Symptom | Cause | Fix |
|---|---|---|
| `UserError: Set the ANTHROPIC_API_KEY environment variable ...` | Key missing | Put it in `<root>/.env` (loaded by `config.py`) or export it; check `LLM_MODEL` matches the provider |
| `ModelHTTPError 404 ... model ... no longer available` | Model name retired for your account | Choose a current vision-capable model for your provider and set `LLM_MODEL` |
| `429 ... GenerateRequestsPerDayPerProjectPerModel-FreeTier` | Free-tier daily cap (about 20 requests per model per day) | Not retried by design. Wait for the reset, use another model/key, or use `--limit` |
| `503 ... high demand` | Provider overload | Retried (6 attempts, up to 30 s waits). If persistent, retry later; affected receipts show "Missing vendor, date, amount" |
| `httpx2.ConnectError` | Transient network drop | Retried automatically; re-run if it persists |
| `ModuleNotFoundError: No module named 'app'` | pytest started outside `backend/` | `cd backend` (pytest.ini sets `pythonpath = .`) |
| `ModuleNotFoundError: pymupdf` / `fitz` | Package missing | `pip install pymupdf`; the code imports `pymupdf` |
| `ImportError: httpx2` | pydantic-ai 2.x not installed | `pip install "pydantic-ai==2.54.0"` |
| `AttributeError ... load_default(size)` | Pillow < 10.1 | `pip install -U pillow` |
| Upload endpoint 500 about forms | `python-multipart` missing | `pip install python-multipart` |
| `FileNotFoundError ground_truth.json` in `test_claim.py` / `test_finance.py` / `factories.py` | Generator not run | Stage 1 |
| `test_api.py` shows 8 skipped | AI caches cold for the configured `LLM_MODEL` | Stage 7 warm-up with the same `LLM_MODEL` |
| A `test_api.py` assertion about a category/outcome fails but others pass | A different model judged a bill differently | Compare with the pipeline table; if reasonable, report it (do not silently edit) |
| `ruff format --check` wants changes | Files were edited after formatting | `ruff format backend tools` (formatting only changes whitespace/wrapping) |
| Coverage below 95% | A test file was not created or a test was skipped | Check Stage 6 file list and that Stage 7 warmed the caches |
| UI shows `Processing failed: The AI model is not configured ...` | No API key | Add the key (or this is the intended safe demo mode) |
| Policy edit returns 502/503 | Re-interpretation failed (quota, no key, grounding failed 3 times) | The previous text is restored automatically; retry or use a stronger model |
| Mermaid diagram shows as code on GitHub | Fence is not exactly three backticks + `mermaid` | Fix the fence |
| README images broken on GitHub | `docs/screenshots/*.jpg` missing | Capture the five screenshots (section 4 of `09_...`) |
| Port 8000 busy | Another server | Use `--port 8001` and open that port |
| Receipt dates make everything "too old" | Real date is > 60 days after Sept 2026 | Start with `CLAIM_TODAY=2026-10-12` |
| `lsof` not found (Windows) | n/a | Use Task Manager / `Get-NetTCPConnection` |
