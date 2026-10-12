# Evaluation Criteria Mapping

How this submission addresses each rule and evaluation criterion, with pointers to the evidence and an honest note on weaknesses.

## Rules checklist
| Rule | Status | Evidence |
|---|---|---|
| 1. Project completion: fully functional, meets objectives | Done | Working app and demo flow; all six added AI requirements implemented (`docs/TECHNICAL_DESIGN.md` section 2) |
| 2. Documentation: overview + track, architecture/flow diagrams, setup + deployment, code explanations + assumptions | Done | `docs/TECHNICAL_DESIGN.md` (sections 1, 3 to 6, 8, 9), `docs/SETUP_AND_DEPLOYMENT.md`, `README.md` |
| 3. Demo video on YouTube | Guide and script provided; **the author records and uploads it** and pastes the URL in the README | `docs/DEMO_VIDEO_GUIDE.md` |
| 4. Personal GitHub with all documents and the video link, no access requests | Procedure and checks provided | `docs/SUBMISSION_CHECKLIST.md` (public repository, incognito check, CI) |
| 5. Comprehensive unit tests | Done | 133 tests, 100% statement coverage, CI (`docs/TEST_REPORT.md`) |
| If hosted, share the link | Optional; Docker and a safe no-key hosting mode are documented | `docs/SETUP_AND_DEPLOYMENT.md` section 6 |
| Personal-account boundaries (no company data, no PII, no secrets, synthetic data) | Respected | `DATA_POLICY.md`; fictional company, policies, employee and receipts; `.env` ignored; secret scan in the checklist |

## 1. Innovation and creativity
* **Policy as a document, interpreted by AI, enforced by code.** No policy value exists in the source. Editing one sentence changes the outcome (hotel 5,000 to 7,000 moves the reimbursable total from INR 23,053 to INR 26,549) with no code change.
* **Grounding check on AI-extracted rules.** Each rule must carry a verbatim quote from its clause, and its number must appear in that quote, or it is returned to the model for correction. This turns an LLM reading of policy into something safe enough for money.
* **Decisions that cite their sources.** Every outcome shows the clause reference, the exact quote, the arithmetic and what is still needed; the chat agent can search the policy and cite it.
* **Minimum-question design.** 24 bills produce 5 questions (one purpose per trip, none for already-rejected bills, clarification only when it changes the outcome).
* **Evidence-driven decisions.** Image hashing for duplicates was measured and rejected; classifier over-asking was found by running the system and fixed.
* *Honest note:* the individual techniques (structured output, RAG, tool-using agent) are established; the novelty is their combination under a deterministic enforcement layer.

## 2. Technical complexity
* **Multi-stage AI pipeline:** vision extraction with validated structured output and per-field confidence; LLM policy interpretation into a typed constraint model; LLM classification with reasoning and abstention; tool-using chat agent; BM25 retrieval over policy clauses (own implementation).
* **Reliability engineering around the models:** output-validator retries (Pydantic AI `ModelRetry`), exponential back-off with quota awareness, per-file failure isolation, content-hash caching, offline demo path, provider-agnostic model string (verified on Claude and on Gemini's free tier).
* **A deterministic decision engine** with grade-specific limits, per-receipt/night/day/month units, shared usage trackers, partial reimbursement, approvals, age limits, exclusions and FX conversion.
* **Concurrency:** four receipts processed in parallel; a background task with progress polling.
* *Honest note:* no model training or fine-tuning; this is deliberate (policy changes must not require retraining).

## 3. Code quality
* `ruff` (pycodestyle, pyflakes, isort, bugbear, pyupgrade) passes on `backend/` and `tools/`; consistent formatting (`ruff format`); config in `pyproject.toml`.
* Small, single-purpose modules and functions (largest module `claim.py`, about 370 lines; longest function 53 lines, with `build_claim` split into `_triage`, `_assess_item`, `_purpose_questions` and `_assemble`); pure functions (`build_claim`, `evaluate_line`, `grounding_problems`) with I/O at the edges; dependency injection of agents and settings; typed models throughout; docstrings state intent and non-obvious decisions.
* No policy-specific constants in code; constants are named and documented (`MIN_CONFIDENCE`, `CLARIFY_BELOW_CONFIDENCE`, `VENDOR_SIMILARITY`, `GAP_DAYS`).
* Error handling returns explicit, user-readable results; no bare excepts; exceptions are chained.
* CI runs lint, tests and a coverage gate on every push.
* *Honest note:* the UI is one 350-line JavaScript file by design (no build step) and has no automated tests; `claim.py` is the largest module because it owns all claim rules.

## 4. Testing and reliability
* 133 offline unit, component, integration and API tests; **100% statement coverage** of the application package; all error branches exercised; LLM behaviour simulated with scripted fake models, including bad outputs.
* Live evaluation against ground truth on 24 synthetic bills: extraction 24/24, classification 23/24, duplicates 3/3 (`docs/TEST_REPORT.md` section 6, `data/eval/`).
* Reliability features tested: retry/no-retry rules, cache behaviour, failure isolation, restore of the previous policy after a failed edit, refusal to submit an incomplete claim, no double submission.
* *Honest note:* coverage is statement coverage, not branch coverage; the UI JavaScript and the Docker image are verified manually or not at all (stated in the report); accuracy is measured on synthetic data only.

## 5. Documentation
* `README.md` (overview, track, results, quick start, document index), `docs/TECHNICAL_DESIGN.md` (overview, requirements traceability, **eight Mermaid diagrams**, AI design, claim logic, data model, API, code walkthrough, assumptions, security, testing, future work), `docs/SETUP_AND_DEPLOYMENT.md`, `docs/TEST_REPORT.md`, `docs/BUSINESS_IMPACT.md` (assumptions stated), `docs/DEMO_VIDEO_GUIDE.md`, `docs/SUBMISSION_CHECKLIST.md`.
* Every claim in the documents was checked against the running system (numbers, diagrams render, no-key hosting mode, cold-cache behaviour).

## 6. Demo quality
* A shot-by-shot script (about 5 minutes) mapped to the criteria: problem and track, architecture, drop bills, explanations with clause quotes, **policy edit changing the outcome live**, answering and submitting, tests and coverage on screen, documentation.
* Preparation steps (dry run so the policy edit is instant on camera, clean browser profile, no secrets on screen), recording settings, editing tips, YouTube upload steps (Unlisted or Public, incognito check), a description template with chapters (`docs/DEMO_VIDEO_GUIDE.md`).
* *Honest note:* the video itself is recorded by the author; this repository contains the plan and the script, not the recording.
