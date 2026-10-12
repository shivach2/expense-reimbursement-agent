# 09 — Documentation, demo video, GitHub submission and evaluation criteria

The competition's rules require more than working code. This file lists exactly what must exist in the rebuilt repository, which parts the agent can
produce, and which parts only the human can do (record the video, create the GitHub repository, fill in links). **The agent must not skip this file:
the documents are part of the grade.**

## 1. The competition rules (verbatim summary) and how this pack satisfies each

| Rule | Requirement | Where it is satisfied |
|---|---|---|
| 1 Project completion | Fully functional, meets all objectives, submitted by **12 Oct 2026** | Stages 0 to 8 of `08_...`; the six AI requirements in `01_...` |
| 2 Documentation | A detailed **technical design document** with: (1) project overview **including the track selected**, (2) **system architecture diagrams** (e.g. flow diagrams), (3) **setup and deployment instructions**, (4) **code explanations and assumptions** | `docs/TECHNICAL_DESIGN.md` (sections 1, 3-6, 8, 9), `docs/SETUP_AND_DEPLOYMENT.md`, `README.md` — all in appendix `A5` |
| 3 Demo video | A **YouTube link** to a demo that highlights key features and the user experience | `docs/DEMO_VIDEO_GUIDE.md` (script, preparation, upload) — **human records and uploads** |
| 4 Submission platform | Code on a **personal GitHub**, link shared **with all documents and the video**; do not ask for access permissions to any platform | `docs/SUBMISSION_CHECKLIST.md` — **human creates a public repository and pushes** |
| 5 Evaluation | Innovation and creativity · Technical complexity · Code quality · Testing and reliability · Documentation · Demo quality; **comprehensive unit tests** are mandatory; if hosted, share the link | `docs/EVALUATION_MAPPING.md`, `docs/TEST_REPORT.md`, Docker files |

**Track selected: Track 1 — "Expense & Reimbursement Agent".** State this in the first lines of the README and in section 1 of the design document (the appendix
files already do).

## 2. What the final repository must contain (checklist the agent verifies)

```
README.md                       overview, TRACK, links table (video/hosted/author placeholders), doc index, architecture diagram, results, quick start
DATA_POLICY.md                  synthetic-data statement (generic wording; no employer name)
docs/TECHNICAL_DESIGN.md        overview+track, requirements traceability, 8 Mermaid diagrams, AI design, claim logic, data model, API, code walkthrough, assumptions, security, testing, future work
docs/SETUP_AND_DEPLOYMENT.md    prerequisites, install (macOS/Linux/Windows), configuration table, run, cache warm-up, tests/coverage/lint, Docker, hosting (safe no-key mode), troubleshooting
docs/TEST_REPORT.md             measured test/coverage/lint numbers, strategy, per-file and per-module tables, honest limits, live-LLM evaluation, defects found and fixed
docs/EVALUATION_MAPPING.md      each rule and each evaluation criterion mapped to evidence, with honest notes
docs/BUSINESS_IMPACT.md         measured results + assumption-labelled time-saving model
docs/DEMO_VIDEO_GUIDE.md        shot list, word-for-word script, preparation, recording, YouTube upload steps, description template
docs/DEMO_SCRIPT.md             pointer to the guide + start commands
docs/SUBMISSION_CHECKLIST.md    GitHub steps, confidentiality greps, screenshots, verification, message template
docs/screenshots/               01_claim_and_chat.jpg 02_explainable_decision.jpg 03_policy_ai_interpreted.jpg 04_policy_changed_no_code.jpg 05_submitted.jpg   (HUMAN/AGENT captures; see section 4)
Dockerfile  .dockerignore  docker-compose.yml  pyproject.toml  .github/workflows/ci.yml  backend/requirements-dev.txt
```

## 3. Verifying the documents (the agent does this, with evidence)

1. **All 8 Mermaid diagrams must parse.** They are in `docs/TECHNICAL_DESIGN.md` (and the first one in the README). GitHub renders them natively. To verify locally,
   serve a tiny HTML page that loads Mermaid from `https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs` and calls `mermaid.parse()` and `mermaid.render()` on each
   ```mermaid` block; every one must return OK. If a diagram fails, fix the syntax in place (quote labels containing punctuation).
2. **Numbers in the documents must match reality.** After Stage 9 compare: tests (`133`), statement count and coverage (`100%`, ~1,380 statements), the 24-receipt results, and the
   quoted line counts. If your run differs (for example a different model changes classification 23/24), **update the documents to the measured values**; never leave claims you did not observe.
3. **Placeholders** remain on purpose for the human: `YOUR_YOUTUBE_URL`, `YOUR_HOSTED_URL`, `YOUR_NAME` (README) and `<YOUR GITHUB REPO URL>` (video guide). List them in your final report.
4. **Link check:** every relative link in `README.md` and `docs/*.md` must resolve to an existing file (`docs/screenshots/*.jpg` excepted until screenshots exist).
5. **Safe-hosting claims** (SETUP_AND_DEPLOYMENT section 6) can be re-verified offline: run the API with `ANTHROPIC_API_KEY=""` → demo, policy view, explanations and submit-gating work; chat and policy edits
   return HTTP 503 "The AI model is not configured"; a new upload ends with status `error` and the same wording.
6. **CI parity:** copy the project (without `.venv`, `.env`, `backend/runtime`) to a temp folder and run `ruff check backend tools` then, from `backend/`,
   `ANTHROPIC_API_KEY=ci-dummy-key LLM_MODEL=<your model> python -m pytest -q --cov=app --cov-fail-under=95` — must pass with warm caches.

## 4. Screenshots (the README embeds five)
They are binary files and are **not** part of this text pack. After Stage 8, capture them from the running app (browser width about 1280-1400 px) and save them under the exact names:

| File | Capture |
|---|---|
| `01_claim_and_chat.jpg` | Claim page after "Try with the demo receipts" and after asking the chip "Why was my hotel reduced?" (chat answer visible beside the claim and the questions list) |
| `02_explainable_decision.jpg` | The expanded **Why?** panel of the Lotus Grove Hotel (15 Sep) bill: category reasoning, policy decision, `GE-2.2` and `TEP-2.1` quotes, extraction confidence |
| `03_policy_ai_interpreted.jpg` | Policy tab before editing (the "What the AI extracted" table) |
| `04_policy_changed_no_code.jpg` | Policy tab after changing `INR 5,000 per night` to `INR 7,000 per night` and saving (status line `Reimbursable total: ₹23,052.68 → ₹26,548.68. No code was changed.`, lodging row `₹7,000 per night`) |
| `05_submitted.jpg` | Claim page after submit: chip `Submitted · RMB-...` and the chat confirmation |

If the agent can drive a browser it may capture them; otherwise the human does. Then `python tools/make_deck.py` (needs `python-pptx`) builds the 10-slide deck `docs/Expense_Agent_Deck.pptx`
(missing screenshots become grey placeholders, so the deck still builds).

## 5. Demo video (human task; the agent prepares everything)

* Follow `docs/DEMO_VIDEO_GUIDE.md`: about 5 minutes; the script is word for word; shows the track, the architecture diagram, uploading the 24 bills, the claim, **an explanation with a policy clause and quote**, the **policy edit (5,000 → 7,000) changing the claim**, answering and submitting, the Finance tab, a terminal with
  `python -m pytest -q --cov=app` (133 passed, 100%) and `ruff check`, and the documentation on GitHub.
* **Before recording, dry-run the policy edit once** so the re-interpretation is cached (otherwise the first edit waits 10-20 s for the LLM on camera).
* YouTube visibility must be **Unlisted or Public** (never Private); verify the link in an incognito window; paste it into the README "Demo video" row; commit and push.
* The agent's deliverable here: confirm the guide's numbers match the measured numbers (133 tests, 100%, 23,053 → 26,549, 5 questions) and that the demo steps work on this build.

## 6. GitHub submission (human task; the agent prepares everything)

1. The agent runs the confidentiality checks from `docs/SUBMISSION_CHECKLIST.md` (secret patterns, no tracked `.env`, your own employer-term grep) and reports the output.
2. The agent makes sure `data/synthetic/` and `data/cache/` are **not** git-ignored (both are synthetic; they let CI and the offline demo work) and that `backend/runtime/`, `.env`, `.venv/` and `submission/` are ignored.
3. The human creates a **public** repository on their **personal** GitHub account, then runs the `git init / add / commit / branch -M main / remote add / push` commands from the checklist (a personal access token or `gh auth login`).
4. Verify in an incognito window: README renders with diagrams and images, no access prompt, Actions workflow green.
5. Send the message template from the checklist: repository link, design-document link, YouTube link, optional hosted link, track statement, synthetic-data statement.
   **Do not request permissions for any platform; make everything public/unlisted.**

## 7. Hosting (optional)
Docker files are provided and **untested in the authoring environment** (Docker was not installed). If Docker is available, the agent should run `docker build -t expense-agent .` and
`docker run --rm -p 8000:8000 -e CLAIM_TODAY=2026-10-12 expense-agent` (no key: safe demo mode) and confirm `GET /api/health`; report the result honestly either way.
Recommended public mode: **no API key** (the demo button, explanations and policy viewer work from cached results; no spend; no abuse risk because the app has no authentication).

## 8. Evaluation criteria — what a grader looks for and where to point them

| Criterion | Strongest evidence | Honest caveat to keep in the docs |
|---|---|---|
| Innovation and creativity | Policy-as-document with a quote-grounding check; edit a sentence and the claim changes with no code; clause-cited explanations; 5 questions for 24 bills | Techniques are established; novelty is the combination under a deterministic layer |
| Technical complexity | Multi-stage LLM pipeline, structured outputs with validator retries, BM25 retrieval, tool-using agent, deterministic evaluator with 4 limit units, back-off and caching, concurrency, model-agnostic | No model training (deliberate) |
| Code quality | `ruff` clean, formatted, typed, small functions (longest 53 lines), pure functions, dependency injection, no policy values in code, CI | UI is a single JavaScript file |
| Testing and reliability | 133 offline tests, 100% statement coverage, every error branch, scripted fake LLMs, CI coverage gate, live evaluation vs ground truth | Statement (not branch) coverage; UI and Docker not unit-tested; accuracy measured on synthetic data |
| Documentation | Design doc with 8 diagrams, setup + Docker, test report, evaluation mapping, honest limits | – |
| Demo quality | Script mapped to the criteria, dry-run advice, upload steps | The video is recorded by the human |
