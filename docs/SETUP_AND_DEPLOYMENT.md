# Setup and Deployment

Everything needed to install, configure, run, test and host the Expense & Reimbursement Agent.

## 1. Prerequisites
| Need | Detail |
|---|---|
| Python | 3.11 or newer (developed on 3.14.7; CI uses 3.12; the Docker image uses 3.12) |
| LLM key (only for live AI features) | One vision-capable model: Anthropic `ANTHROPIC_API_KEY` (default), Google `GOOGLE_API_KEY`, or OpenAI `OPENAI_API_KEY` |
| Browser | Any modern browser |
| Optional | Docker 24+ (for the container), Git |

The **demo button works without any key or network** (AI results are cached in `data/cache/`); only uploading new bills, chat and editing the policy call an LLM.

## 2. Local setup

macOS / Linux
```bash
git clone <your-repo-url> expense-agent && cd expense-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt          # add -r backend/requirements-dev.txt for tests and lint
cp .env.example .env                              # then edit .env and add your key
```
Windows (PowerShell)
```powershell
git clone <your-repo-url> expense-agent; cd expense-agent
py -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
copy .env.example .env
```

### Configuration (`.env` at the project root, or real environment variables)
| Variable | Default | Meaning |
|---|---|---|
| `LLM_MODEL` | `anthropic:claude-sonnet-5-5` | Pydantic AI model string `<provider>:<model>`, e.g. `google:gemini-3.8-flash`, `openai:<model>`. Must be vision-capable. Model names change over time: if you get HTTP 404, use a current name |
| `ANTHROPIC_API_KEY` / `GOOGLE_API_KEY` / `OPENAI_API_KEY` | – | Key for the provider in `LLM_MODEL` |
| `CLAIM_TODAY` | real date | Pins "today" for the 60-day receipt-age rule so the demo data (September 2026) stays valid. Use `2026-10-12` |
| `LLM_CALL_DELAY_S` | `0` | Pause after each extraction (helps free-tier rate limits) |
| `USE_EXTRACTION_CACHE` | `false` | Read cached extraction results in the CLI tools (the demo endpoint always does) |

## 3. Run
```bash
cd backend
CLAIM_TODAY=2026-10-12 uvicorn app.main:app --port 8000      # Windows PowerShell: $env:CLAIM_TODAY="2026-10-12"; uvicorn app.main:app --port 8000
```
Open **http://localhost:8000**. Interactive API docs: http://localhost:8000/docs. Health check: `GET /api/health`.

### First run on a new machine: warm the AI caches
The AI result caches are keyed by content hash and by model. If you changed `LLM_MODEL`, or regenerated the synthetic receipts (PDF bytes contain
timestamps), warm the caches once (about 50 LLM calls, 1-3 minutes):
```bash
python tools/run_pipeline.py --today 2026-10-12      # run from the project root
```
This also prints the claim table and accuracy against ground truth, and writes `data/eval/<model>.json`.

## 4. Tests, coverage and lint
```bash
pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q                                       # 133 tests, offline, about 4 s
python -m pytest -q --cov=app --cov-report=term-missing   # coverage (100% of app/ statements)
cd .. && ruff check backend tools && ruff format --check backend tools
```
If the AI caches are cold for your `LLM_MODEL`, the 8 tests in `tests/test_api.py` are **skipped with a message** (not failed); warm the caches as above.

## 5. Docker
Build and run (the image contains the code, the UI, the policy documents and the committed AI caches):
```bash
docker build -t expense-agent .
docker run --rm -p 8000:8000 --env-file .env -e CLAIM_TODAY=2026-10-12 -v expense-runtime:/app/backend/runtime expense-agent
```
or with Compose (requires a `.env` file):
```bash
docker compose up --build
```
The named volume keeps uploads, the finance SQLite file and the runtime copy of the policies across restarts. A health check calls `/api/health`.
> The Dockerfile follows standard patterns but was **not built in the authoring environment** (Docker was not installed there). If the build
> fails on your machine, run locally as in section 3 and tell the reviewers; nothing else depends on Docker.

## 6. Hosting the demo (optional; "if hosted, share the link")
Any platform that runs a Docker image works (Render, Railway, Fly.io, a VM with `docker compose`). Generic recipe:
1. Push the repository to GitHub and create a **Web Service from the repository's Dockerfile**.
2. Environment variables: `LLM_MODEL`, the provider key (as a *secret*), `CLAIM_TODAY=2026-10-12`.
3. Attach a persistent disk/volume at `/app/backend/runtime` (optional; without it, submitted claims reset on redeploy).
4. Port `8000`; health-check path `/api/health`.
5. Share the service URL.

**Choose a hosting mode deliberately (the app has no authentication):**
| Mode | How | Trade-off |
|---|---|---|
| **Safe demo mode (recommended for a public link)** | Do **not** set a provider key | The demo button, the claim view, "Why?" explanations, the policy viewer and submission to the mock finance system all work from the cached AI results. Uploading new bills, chat and policy edits return a clear "AI model is not configured" message. No spend, no abuse risk |
| Full live mode | Set the key | Everything works, but anyone with the URL can spend your API credits. Put it behind basic auth or a reverse proxy with a password, set a spend limit on the key, and use it only for the review window |

Never put real receipts or real policies into a hosted instance: data is synthetic by design (`DATA_POLICY.md`).

## 7. Regenerating the synthetic data
```bash
python tools/generate_receipts.py        # rewrites data/synthetic/receipts/* and ground_truth.json (24 files)
```
Then warm the caches again (section 3). Commit `data/synthetic/` and `data/cache/` together so receipts and cached results stay consistent.

## 8. Project layout
```
backend/app/       application code (ingest, extraction, policy/*, classifier, claim, pipeline, state, chat, finance, main)
backend/tests/     133 tests (+ factories.py shared builders)
frontend/          single-page UI
tools/             data generator, evaluation CLI, deck builder
data/policies      fictional policy documents      data/employees   fictional employee
data/synthetic     generated receipts + ground truth     data/cache   cached AI results     data/eval   metrics
docs/              design, setup, test report, evaluation mapping, demo and submission guides
Dockerfile  docker-compose.yml  pyproject.toml (ruff)  .github/workflows/ci.yml
```

## 9. Troubleshooting
| Symptom | Fix |
|---|---|
| "The AI model is not configured" in the UI | Add the key to `.env` and restart; or this is the intended safe demo mode |
| HTTP 404 model not found | Set `LLM_MODEL` to a model your account can use |
| HTTP 429 with `PerDay` | Free-tier daily quota reached (not retried by design). Wait, switch model/key, or use cached demo |
| HTTP 503 "high demand" | Provider overload; the app retries with back-off, then reports it |
| `ModuleNotFoundError: app` when testing | Run pytest from `backend/` |
| Everything is "too old" | Start with `CLAIM_TODAY=2026-10-12` |
| `test_api.py` shows 8 skipped | Warm the caches (section 3) |
| Port 8000 busy | `--port 8001` |
