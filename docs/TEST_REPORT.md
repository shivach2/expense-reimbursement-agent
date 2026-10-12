# Test Report

All numbers below were measured on the final code (Python 3.14.7, pytest 9.1, pytest-cov, ruff).

## 1. Summary
| Measure | Result |
|---|---|
| Automated tests | **133 passed, 0 failed, 0 skipped** (with warm AI caches) |
| Run time | about 4 seconds, **fully offline** (no LLM call, no network, no API key needed) |
| Statement coverage of `backend/app` | **100%** (1,380 statements, 0 missed), enforced at >= 95% in CI |
| Lint (`ruff`: pycodestyle, pyflakes, isort, bugbear, pyupgrade) | All checks passed |
| Live LLM evaluation (24 synthetic receipts, ground truth) | extraction 24/24, classification 23/24, duplicates 3/3 (details in section 6) |

Reproduce:
```bash
pip install -r backend/requirements-dev.txt
cd backend
python -m pytest -q --cov=app --cov-report=term-missing
cd .. && ruff check backend tools && ruff format --check backend tools
python tools/run_pipeline.py --today 2026-10-12      # live-LLM evaluation (needs an API key; writes data/eval/<model>.json)
```
On a cold checkout (no cached AI results for the configured `LLM_MODEL`) the 8 tests in `test_api.py` are **skipped with an explanatory message** rather than failing;
`python tools/run_pipeline.py --today 2026-10-12` warms the caches.

## 2. Test strategy
The suite has four layers. None of them calls a real LLM, which keeps the tests fast, free and deterministic.

| Layer | What it checks | How the LLM is replaced |
|---|---|---|
| Unit | Pure logic: ingestion, quality rules, currency, duplicates, grouping, clause parsing and BM25, policy evaluator, grounding check | not needed |
| Component | Agents with retries and validation: extraction, policy interpreter, classifier, chat tools | Pydantic AI `FunctionModel` and `TestModel` return scripted outputs, including *bad* outputs to prove the retry and fallback paths |
| Integration | The whole claim builder over the 24 synthetic receipts, using ground truth as a perfect extractor and classifier; policy changes; answering questions to reach READY | ground-truth fixtures |
| API | Every endpoint, success and error branches (400/404/409/413/415/422/502/503), upload path, policy edit and restore, submit and finance, background-processing failures | fake pipeline or cached AI results |

Design choices that make the tests meaningful:
* The hand-written policy fixture used by the evaluator tests is **cross-checked against the real policy documents** with the same grounding check the interpreter uses, so the fixture cannot drift from the documents.
* Behaviours with a privacy or correctness consequence have explicit tests: EXIF is stripped; the file name is never sent to the model; a daily-quota 429 is not retried; a rejected receipt asks no questions; the 60-day boundary (60 passes, 61 fails).
* Hallucination handling is tested for every kind (non-verbatim quote, wrong amount, missing clause, undefined category, wrong age), plus the LLM retry loop and the final error when retries are exhausted.
* Policy adaptation is tested at three levels: evaluator (limit 5,000 vs 7,000), state (re-evaluating live sessions after a policy reload), and API (edit the document, claim changes, reset restores).

## 3. Tests per file (133)
| File | Tests | Focus |
|---|---|---|
| `test_ingest.py` | 7 | JPEG re-encode and downscale, EXIF stripped, PDF rasterised, hashing, unsupported and corrupt files |
| `test_quality.py` | 8 | review reasons, confidence only when a value is present, line-item sums with and without tax, currency normalisation |
| `test_extraction.py` | 8 | structured output, caching, FX, cache hit skips the LLM, invalid output becomes an error result, filename never sent, retry and no-retry rules |
| `test_duplicates.py` | 8 | identical file, same bill, spelling tolerance, bill-number guard, exempt files |
| `test_grouping.py` | 1 | trip grouping and titles |
| `test_policy_evaluator.py` | 15 | every branch of the decision procedure, grade-specific and monthly limits, approvals, age boundary |
| `test_policy_interpreter.py` | 11 | grounding of the fixture, hallucination catches, LLM retry, hash cache and re-interpretation, merge, clause parsing, BM25 |
| `test_classifier.py` | 6 | classification, caching, prompt content, retry on unknown category, fallback, unreadable skips the LLM |
| `test_claim.py` | 12 | end-to-end over 24 receipts: planted problems found, minimal questions, hotels partially reimbursed, ready after answers, policy change, ambiguous category, overrides |
| `test_edge_cases.py` | 10 | no entitlement, no limit, partial monthly limit exhausted, low-confidence confirm, unsupported currency, wrapped clauses, prompt contents, call delay, pipeline failure isolation |
| `test_state.py` | 15 | every answer kind, validation errors, name collisions, error reporting (including missing API key), reload recomputes claims |
| `test_chat_helpers.py` | 6 | agent tools without receipts, record-answer validation, explain with clauses, lazy agent and history, summaries |
| `test_finance.py` | 4 | SQLite submission, references, refusal when not ready |
| `test_api.py` | 8 | demo flow, thumbnails, answer then submit then finance, bad inputs, policy edit changes the claim, scripted chat agent |
| `test_api_upload_and_errors.py` | 14 | upload success, limits, concurrency refusals, AI-failure mapping, policy failure and restore, health, env handling |

## 4. Coverage by module (statements)
| Module | Statements | Missed | Cover |
|---|---|---|---|
| `chat.py` | 90 | 0 | 100% |
| `claim.py` | 212 | 0 | 100% |
| `classifier.py` | 63 | 0 | 100% |
| `config.py` | 21 | 0 | 100% |
| `currency.py` | 7 | 0 | 100% |
| `duplicates.py` | 54 | 0 | 100% |
| `extraction.py` | 65 | 0 | 100% |
| `finance.py` | 36 | 0 | 100% |
| `grouping.py` | 24 | 0 | 100% |
| `ingest.py` | 54 | 0 | 100% |
| `main.py` | 177 | 0 | 100% |
| `models.py` | 40 | 0 | 100% |
| `pipeline.py` | 32 | 0 | 100% |
| `policy/clauses.py` | 73 | 0 | 100% |
| `policy/evaluator.py` | 89 | 0 | 100% |
| `policy/interpreter.py` | 93 | 0 | 100% |
| `policy/schema.py` | 79 | 0 | 100% |
| `quality.py` | 29 | 0 | 100% |
| `state.py` | 139 | 0 | 100% |
| **Total** | **1,380** | **0** | **100%** |

## 5. What the tests do not prove (honest limits)
* **Coverage is not correctness.** 100% of statements executing under test shows nothing is untested, not that every behaviour is right. Branch coverage was not measured.
* **LLM quality is measured separately**, on synthetic data only (section 6). Real receipts will be messier.
* **The web UI (about 350 lines of JavaScript) has no automated tests.** It was verified manually in a browser (demo flow, answers, chat, policy edit, submit, finance tab).
* **`tools/` scripts** (data generator, evaluation CLI, deck builder) are exercised by running them, not by unit tests, and are excluded from the coverage figure.
* **The Docker image was not built** in the authoring environment (Docker was not installed). The Dockerfile follows standard patterns.
* **No load or security testing** was done. The app has no authentication by design (prototype).

## 6. Live-LLM evaluation (`tools/run_pipeline.py`, 24 synthetic receipts, ground truth)
Claude Sonnet 5.5, run on 12 Oct 2026 with `--today 2026-10-12`:

| Metric | Result |
|---|---|
| Vendor, date, total, currency extracted correctly | 24/24 each (clean, photographed, blurry, crumpled, PDF, USD and SGD) |
| Category matches ground truth | 23/24 (miss: a 4-person tasting menu classed as client entertainment, arguably correct) |
| Duplicates found (exact copy and two re-photographed bills) | 3/3, no false alarms |
| Bills excluded by policy with clause (expired, personal) | 2/2 expected, plus the arguable tasting menu |
| Questions asked | 5 for 24 bills |
| Policy edit (hotel limit 5,000 to 7,000) | reimbursable INR 23,052.68 to INR 26,548.68, no code change |

Gemini 3.8 Flash (free tier): interpreted the policy identically; of 8 receipts attempted, 5 completed and all 5 were correct on every field and category; 3 failed with
HTTP 503 "high demand". No full-set figure is claimed for it (`data/eval/google_gemini-3.8-flash.json` records this).

## 7. Defects found by running the system for real (and fixed)
| Finding | How it was found | Fix |
|---|---|---|
| Classifier asked 4 unnecessary clarification questions (parking, conference fee, train ticket, client lunch), one about tax | First full run showed 8 questions | Tightened instructions and added a confidence guard (< 0.75): 8 questions became 5 |
| Image hashing flagged different bills as duplicates (distance 0) and missed a re-photographed one (distance 34) | Measured on the synthetic set before relying on it | Replaced by content-based duplicate detection with a bill-number guard |
| Free-tier daily quota error was retried uselessly; 503/connection drops crashed a batch | Gemini free-tier runs | Back-off for transient errors only; daily quota not retried; one bad file never aborts the batch |
| Raw markdown asterisks in chat replies | Browser check | Render `**bold**` as `<b>` nodes in the UI |
| Upload without an API key showed a raw exception text | Simulated a keyless deployment | Friendly "AI model is not configured" message, with a test |
| Documentation drift (stale references to removed files and counts) | Documentation sweep | Corrected |
| Untested code paths in the upload endpoint and error branches (82% coverage in `main.py`) | Coverage report | 45 more tests; coverage 100% |
