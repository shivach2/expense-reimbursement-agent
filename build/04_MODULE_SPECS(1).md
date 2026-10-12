# 04 — Module specifications (behaviour, constants, edge cases)

Use this document to **understand and verify** the code in the appendix. The appendix is authoritative.
All paths are relative to the project root. "LLM" means a Pydantic AI agent call.

---
## backend/app/config.py
* `ROOT = Path(__file__).resolve().parents[2]` (project root). `load_dotenv(ROOT / ".env")` at import.
* `@dataclass(frozen=True) Settings` fields: `llm_model: str`, `llm_call_delay_s: float`, `use_extraction_cache: bool`,
  `cache_dir: Path` (required, no default), then defaults: `policy_cache_dir = ROOT/data/cache/policy`,
  `classification_cache_dir = ROOT/data/cache/classification`, `policy_dir = ROOT/data/policies`,
  `employee_path = ROOT/data/employees/emp_demo_m2.json`, `max_image_side = 1600`, `max_pdf_pages = 3`.
* `get_settings()` reads `LLM_MODEL` (default `anthropic:claude-sonnet-5-5`), `LLM_CALL_DELAY_S` (default 0),
  `USE_EXTRACTION_CACHE` (`"true"` case-insensitive → True) and sets `cache_dir = ROOT/data/cache/extractions`.
* Tests construct `Settings(...)` directly with `cache_dir=tmp_path/...`; defaults must therefore exist for the
  policy/classification fields.

## backend/app/models.py
* `LineItem(description: str, amount: float | None = None)`.
* `FieldConfidence(vendor, date, total)`: floats, `0 <= x <= 1`, each with a description for the LLM.
* `Receipt`: `readable: bool`; `vendor: str|None`; `receipt_date: datetime.date|None` (field is named `receipt_date`, **not**
  `date`, to avoid shadowing the `date` type); `total: float|None`; `tax: float|None`; `currency: str`;
  `category: str` (free-text hint such as "restaurant meal" — **not** an enum); `nights: int|None`;
  `line_items: list[LineItem]` (default empty); `receipt_number: str|None`; `payment_method: str|None`;
  `confidence: FieldConfidence`; `notes: str|None`. Field descriptions are part of the LLM schema (see `05`).
  A `field_validator("currency")` strips, upper-cases and raises `ValueError` unless exactly 3 letters
  (so `" usd "` → `"USD"`, `"US"` is rejected → LLM retry).
* `ExtractedReceipt`: `source_file`, `file_sha256`, `model`, `receipt: Receipt|None`, `total_inr: float|None`,
  `needs_review: bool = True`, `review_reasons: list[str]`, `error: str|None`.

## backend/app/currency.py
`RATES_TO_INR = {INR:1.0, USD:83.0, EUR:90.0, GBP:105.0, SGD:62.0, AED:22.6}` (static, illustrative).
`is_supported(code)` case-insensitive; `to_inr(amount, code)` → `round(amount*rate, 2)` or `None` for unknown codes.

## backend/app/ingest.py
* `IMAGE_EXTS = {.png,.jpg,.jpeg,.webp,.bmp}`, `PDF_EXT = ".pdf"`; `UnsupportedFileError(ValueError)`.
* `Page(data: bytes, media_type="image/jpeg")`, `LoadedFile(name, sha256, pages, embedded_text="")` (frozen dataclasses).
* `_to_page(img, max_side)`: `ImageOps.exif_transpose` → `convert("RGB")` → `thumbnail((max_side,max_side))` →
  save JPEG quality 88. Re-encoding **drops EXIF/GPS** (privacy) — tested.
* `load_bytes(data, filename, *, max_side=1600, max_pdf_pages=3)`: extension decides type (case-insensitive).
  Images: unreadable → `UnsupportedFileError("<name>: not a readable image (...)")`. PDFs: `pymupdf.open(stream=data,
  filetype="pdf")` (any exception → `UnsupportedFileError("<name>: not a readable PDF (...)")`); first `max_pdf_pages`
  pages rendered with `page.get_pixmap(dpi=150)` → PIL RGB → `_to_page`; `embedded_text` = non-empty `page.get_text().strip()`
  values joined with newlines. Anything else → `UnsupportedFileError("<name>: unsupported type '<ext>'")`.
  `sha256` is of the **original uploaded bytes**.
* `load_file(path, **kw)` = `load_bytes(path.read_bytes(), path.name, **kw)`.

## backend/app/quality.py
`assess_receipt(r) -> list[str]` (constants `MIN_CONFIDENCE = 0.7`, `SUM_TOLERANCE = 0.02`):
* not readable → exactly `["Receipt is not readable"]`.
* `"Vendor name missing"`, `"Date missing"`, `"Total amount missing"` for null fields.
* For vendor/date/total **that are present** with confidence < 0.7: `"Low confidence on <vendor|date|total> (0.xx)"`.
* Unsupported currency → `"Unsupported currency XYZ"`.
* If `total` and at least one line-item amount: candidates `sum(items)+tax` and `sum(items)`; if **both** differ from
  total by more than 2% → `"Line items (<sum+tax:.2f>) do not add up to total (<total:.2f>)"`.

## backend/app/extraction.py
* `INSTRUCTIONS` (see `05`). `build_agent(model)` → `Agent(model, output_type=Receipt, instructions=INSTRUCTIONS, retries=2,
  defer_model_check=True)`.
* Cache: file `settings.cache_dir/<slug(model)>/<sha256>.json` where `slug` replaces every run of characters outside
  `[A-Za-z0-9._-]` with `_`. Stored value = `ExtractedReceipt` JSON. **Always written after a successful extraction;
  only read when `settings.use_extraction_cache` is true.** A cache hit returns the cached object with `source_file` replaced
  by the current file name. Failures are never cached.
* `_user_content(loaded)`: `[prompt, *BinaryContent(page.data, media_type=page.media_type)]` where prompt =
  `"Extract the receipt in the attached image(s)."` plus, if the PDF had embedded text,
  `"\n\nText embedded in the PDF (may be incomplete):\n<text>"`. **The file name is deliberately never sent** (it can leak
  the expected answer; there is a test).
* `_run_with_backoff(agent, content, attempts=6, **run_kwargs)`: calls `agent.run(content, **run_kwargs)`; on
  `ModelHTTPError` or `httpx2.TransportError` decides *transient* = transport error, or status in `{429, 503}` **and
  `"PerDay"` not in `str(e.body)`** (a daily quota can't be cured by waiting). Non-transient or last attempt → re-raise;
  else `await asyncio.sleep(min(2 * 2**n, 30))` (2, 4, 8, 16, 30 s). Shared by classifier and interpreter.
* `_finalise(loaded, model, receipt)`: `reasons = assess_receipt(receipt)`; `total_inr = to_inr(total, currency)` when total
  present; `needs_review = bool(reasons)`.
* `extract_receipt(path, *, agent=None, settings=None)`: load file → optional cache read → `agent = agent or
  build_agent(settings.llm_model)` → run with backoff → on `UnexpectedModelBehavior` return an `ExtractedReceipt` with
  `receipt=None`, `needs_review=True`, `review_reasons=["Automatic extraction failed; please enter details manually"]`,
  `error=str(e)` (not cached) → else finalise, write cache, `await asyncio.sleep(settings.llm_call_delay_s)` if non-zero.
  `UserError`, non-transient `ModelHTTPError`, `UnsupportedFileError` propagate.

## backend/app/duplicates.py
`DupKey(file, sha256, vendor, date, total, currency, receipt_number=None)`; constants `VENDOR_SIMILARITY = 0.85`,
`AMOUNT_TOLERANCE = 0.01`. `_norm(s)` = lower-case alphanumerics only. `_same_vendor` = `difflib.SequenceMatcher` ratio of
normalised names ≥ 0.85 (so "Bluebird Cafe" ≈ "BLUEBIRD CAFÉ."). `_same_receipt(a,b)`: false if any of vendor/date/total missing
on either; requires equal date and currency, `|total diff| ≤ 0.01`, similar vendor; and **if both have receipt numbers and
they differ → not duplicates** (two real identical taxi fares). `find_duplicates(keys, exempt=())` walks keys in order,
keeping a list of "originals"; a key is a duplicate of the **first** original with identical sha256 (reason
`"identical file"`) or `_same_receipt` (reason `"same vendor, date and amount"`); exempt files are never reported but can be
originals. Returns `{duplicate_file: DupMatch(original, reason)}`. Image hashing is intentionally not used (docstring explains).

## backend/app/grouping.py
`GAP_DAYS = 3`. `Group(id, start, end, files)` with `title`: single day → `"Expenses on 14 Sep 2026"`, else
`"Expenses 14 Sep – 24 Sep 2026"` (en dash, `%d %b`). `group_by_date(items=[(file, date)], gap_days=3)` sorts by
`(date, file)`; a date within `gap_days` of the current group's end joins it; otherwise a new group with
`id = "g-<ISO start date>"`.

## backend/app/policy/schema.py
Models: `Employee(id,name,grade,role,base_city)` + `load_employee(path)`; `CategoryDef(id,label,description)`;
`_Cited(clause, quote, document="")`; `Entitlement(+category, grades[])`; `Limit(+category, amount, currency="INR", unit, grades|None,
over_limit_action, requires_approval=False)` with `unit ∈ {per_receipt, per_night, per_day, per_month}` and
`over_limit_action ∈ {partial, needs_approval, reject}`; `Exclusion(+category, reason)`; `AgeRule(+max_age_days)`;
`PolicyConstraints(categories, entitlements, limits, exclusions, age_rules)`.
`PolicySet(PolicyConstraints)` adds `documents: dict[name→sha256]`, `merge(parts)` (categories de-duplicated by id, first wins;
other lists concatenated), `category_ids()`, `label(cat)`, `exclusion_for(cat)`, `entitlements_for(cat)`,
`entitlement_for(cat, grade)`, `limit_for(cat, grade)` (candidates where `grades is None or grade in grades`, **grade-specific
sorted first**), `eligible_categories(grade)` = sorted ids with an entitlement listing the grade, minus excluded categories.
`document` is stamped by code, not by the LLM.

## backend/app/policy/clauses.py
`doc_code("travel_expense_policy.md") = "TEP"` (initials of `_`-separated stem words, upper-case); `normalize(s)` =
whitespace-collapsed, casefolded. `parse_clauses(document, text)`: a line `## 3. Meals` sets the heading (number prefix stripped);
a line matching `^(\d+\.\d+)\s+(.*\S)\s*$` starts a clause; following non-blank lines continue it; a blank line ends it.
`Clause.ref = "<DOCCODE>-<number>"` (e.g. `TEP-2.1`). `load_documents(dir)` → `{name: text}` for `*.md` sorted by name.
`ClauseIndex` = BM25 (`k1=1.5, b=0.75`, `idf = ln(1 + (N − df + 0.5)/(df + 0.5))`) over `heading + text`; tokens are lower-case
`[a-z0-9]+` minus a small stop-word set, with a plural stemmer (strip trailing "s" when len>3 and not "ss"); `search(query, k=3)`
returns `[(Clause, score)]` with score>0, best first; no match → `[]`.

## backend/app/policy/interpreter.py
* `INSTRUCTIONS` (see `05`). `PolicyInterpretationError(RuntimeError)`.
* `grounding_problems(constraints, clauses: {number: text}) -> list[str]` — for every entitlement/exclusion/limit/age rule:
  clause must exist (`"<kind>: clause 'X' does not exist in the document"`), `normalize(quote)` must be a substring of
  `normalize(clause text)` (`"<kind> X: quote is not copied verbatim from that clause"`), category must be in
  `constraints.categories` ids (`"<kind> X: category 'c' is not in `categories`"`), limit amount must equal some number found in
  the quote (`"limit X: amount N does not appear in the quote"`), age days must appear in the quote
  (`"age rule X: N does not appear in the quote"`). Numbers are parsed with `\d[\d,]*(?:\.\d+)?` (commas removed).
* `build_interpreter_agent(model)`: `Agent(model, output_type=PolicyConstraints, deps_type=dict, instructions=INSTRUCTIONS,
  retries=3, defer_model_check=True)` + `@agent.output_validator` raising `ModelRetry("Fix these problems and return the full result
  again:\n- ...")` when problems exist; `deps` = `{clause number: clause text}`.
* `interpret_document(name, text, *, known_categories=None, agent=None, settings=None) -> (sha256, PolicyConstraints)`:
  `sha = sha256(text)`; cache key = first 32 hex chars of `sha256(f"{sha}|{','.join(sorted(known))}")`; cache file
  `settings.policy_cache_dir/<slug(model)>/<key>.json` (**always read when present**). Prompt = `"Document file name: {name}\n"` +
  (if known) `"Category ids already defined by other documents (reuse them): a, b\n"` + `"\n--- DOCUMENT ---\n{text}"`.
  After success every item gets `.document = name`; result cached. `UnexpectedModelBehavior` → `PolicyInterpretationError`.
* `load_policy_set(policy_dir, *, agent=None, settings=None) -> PolicySet`: for each `*.md` in sorted order, interpret with the
  accumulated category ids as `known_categories`, then `PolicySet.merge`.

## backend/app/policy/evaluator.py (deterministic)
`Outcome ∈ {approved, partial, flagged, rejected}`; `ClauseCite(ref, document, quote)`; `Decision(outcome, category,
claimed_inr, eligible_inr, explanation, cites, needs)`; `UsageTracker.used: defaultdict(float)` keyed by bucket.
`inr(x)` → `"INR 5,000"` (no decimals when whole) or `"INR 2,016.90"`. `evaluate_line(category, claimed_inr, date, employee,
policy, today, tracker, nights=None, justification=None)` applies, **in this order**:
1. category not in `policy.category_ids()` → `FLAGGED`, eligible 0, `explanation="No policy category matches this expense; please choose one."`, `needs=["category"]`.
2. exclusion for the category → `REJECTED`, `"<Label> is not reimbursable: <reason>. Policy <ref>: \"<quote>\""`, cite the exclusion.
3. no entitlement mentions the category → `REJECTED`, `"No policy clause makes <Label> reimbursable."`.
4. no entitlement lists the employee's grade → `REJECTED`, `"Grade <g> is not eligible to claim <Label>. Policy <ref>: \"...\""` citing the first entitlement.
5. age rule: if `date` and `(today − date).days > max_age_days` → `REJECTED`, `"The receipt is N days old; the limit is M days. Policy ..."`. (Missing date skips this.) Boundary: exactly the limit passes.
6. limit lookup `policy.limit_for(category, grade)`; none → `APPROVED`, eligible = claimed, `"<Label> is reimbursable with no amount limit. Policy ..."`; cites = [entitlement, (limit)].
7. cap in INR (`to_inr(limit.amount, limit.currency)`); `per_night` → cap × max(nights or 1, 1), scope text `"INR 5,000 per night x 1"`; other units scope `"INR 3,000 per day"`.
   Bucket: `per_day` → (doc, clause, date); `per_month` → (doc, clause, year, month); otherwise none. `remaining = max(cap − used[bucket], 0)` for bucketed limits else `cap`.
8. `claimed ≤ remaining + 0.005`: if `requires_approval` and no justification → `FLAGGED`, eligible 0, `needs=["approval reference or justification"]`; else consume bucket, `APPROVED`, `"Within the <scope> limit. Policy ..."`.
9. over the limit by `over = claimed − remaining`: `partial` → consume `remaining`; if `remaining <= 0` → `REJECTED` (`"The <scope> limit is already used up."`) else `PARTIAL`, eligible = remaining,
   `"The bill is INR 7,168 but the limit is INR 5,000 per night x 1. Reimbursing INR 5,000; the excess INR 2,168 is not reimbursable. Policy TEP-2.1: \"...\""`;
   `needs_approval` → with justification: consume, `APPROVED` (`"... approved as an exception on the recorded justification."`), else `FLAGGED` eligible 0, `needs=["manager-approved justification"]`;
   `reject` → `REJECTED`, `"The bill is INR X, above the <scope> limit, and the excess is not reimbursable. Policy ..."`.
`eligible_inr` is rounded to 2 decimals.

## backend/app/classifier.py
`UNKNOWN = "unknown"`. `Classification(category, reasoning, confidence 0..1, needs_clarification=False, clarification_question=None)`.
`unknown_classification(reason)` → category `unknown`, confidence 0, needs_clarification True, question `"What was this expense for?"`.
`build_classifier_agent(model)`: `Agent(model, output_type=Classification, deps_type=set, instructions=INSTRUCTIONS, retries=2, defer_model_check=True)` + output validator that
raises `ModelRetry("category must be one of: ...")` if the category is not in `deps` (the policy's category ids). `describe_categories(policy, employee)` renders one line per category:
`- id: Label. description [available to grade M2]` / `[NOT available to grade E1]` / `[never reimbursable]`. Prompt = employee line + category list + expense facts
(vendor, date, total+currency, line items "desc (amount)" joined by "; ", extractor's description, nights, notes). Cache key = first 32 hex of
`sha256(f"{file_sha}|{sorted(policy.documents.items())}|{grade}|{model}|{INSTRUCTIONS}")`, path `settings.classification_cache_dir/<slug>/<key>.json` (always read when present).
Unreadable/failed extraction → `unknown_classification("The bill could not be read.")` **without calling the LLM**; `UnexpectedModelBehavior` → `unknown_classification("Automatic classification failed.")`.

## backend/app/claim.py
Types: `ItemStatus`, `ClaimState`, `ItemInput`, `ClaimInputs(items: {file: ItemInput}, group_purposes: {group_id: str})`, `ClaimItem`, `ClaimGroup`, `Question(id, kind, target, text, fields, options)`, `Claim`.
`ItemInput.has_corrections()` = any of vendor/receipt_date/total/currency set. Constants `_SOFT_REASON_PREFIXES = ("Low confidence", "Line items")`, `CLARIFY_BELOW_CONFIDENCE = 0.75`.
Structure (all pure functions, longest 53 lines): `_dup_key`, `_new_item`, **`_triage`** (stage 1: duplicates + policy evaluation, returns items, the classification used per file and the receipts still in play), `_missing_basics`, `_category_unclear`, **`_assess_item`** (stage 2: status and questions for one receipt; returns `(questions, needs_business_purpose)`), `_purpose_questions`, **`_assemble`** (stage 3: state, totals, counts) and `build_claim` which orchestrates them. Behaviour:

`build_claim(extracted, classifications, employee, policy, inputs=None, *, today=None)`:
1. Apply corrections per receipt (`_effective`).
2. `find_duplicates` (exempt = items with `not_duplicate`) → items with status `duplicate`, `duplicate_of`, reason `"Duplicate of <orig> (<reason>); left out of the claim"`.
3. For every other item: category = employee override or classification (missing classification → unknown); `evaluate_line` (claimed = `total_inr or 0`, nights from the receipt, justification from inputs, one shared `UsageTracker` in input order).
   `REJECTED` → status `ineligible`, reasons `[explanation]`. Otherwise status `complete` and the item is *active*.
4. Group active items having dates (`group_by_date`).
5. For each active item: **missing basics** (vendor/date/amount, or currency when `total_inr is None` but total present) → `missing_info`, reason `"Missing a, b"`, question `field` with text `"<label>: please provide the date."` (join with " and "), then **skip the rest**.
   Else: *unclear category* (no employee override and ((classification asks clarification **and** confidence < 0.75) or category unknown/not in policy)) → `questionable`, reason `"Category unclear"`, question `clarify` with `options = eligible categories for the grade`;
   elif decision `FLAGGED` → `questionable` + `justify` question `"<label>: <explanation> Please provide <needs joined by ' and '>."`; elif `PARTIAL` → add the explanation to reasons.
   Soft extraction reasons (prefixes above) with no `confirmed` flag and no corrections → `questionable` + `confirm` question.
   Business purpose = item purpose or the group's purpose; if absent: remember the group (if any), reason `"Business purpose needed"`, and a `complete` item becomes `missing_info`.
   `eligible_inr = decision.eligible_inr` unless the decision is `FLAGGED` (then 0).
6. One `purpose` question per group with missing purposes: `"What was the business purpose of these N receipt(s)? (<group title>)"`.
7. `included` = not duplicate/ineligible. State: none included → `blocked`; all `complete` → `ready`; else `needs_input`.
   `claimed_inr` = Σ `total_inr` of included; `eligible_inr` = Σ eligible of included; `eligible_by_category`; `counts` by status value; `groups` with `eligible_inr`.

## backend/app/pipeline.py
`process_files(paths, employee, policy, *, settings=None, concurrency=4, on_progress=None) -> (list[ExtractedReceipt], {file: Classification})`:
one extraction agent and one classifier agent shared; `asyncio.Semaphore(concurrency)`; per file `extract_receipt` then `classify_receipt`; `UnsupportedFileError`, `ModelAPIError`,
`httpx2.TransportError` → a failed `ExtractedReceipt` (`review_reasons=["Could not process this file: <msg[:200]>"]`, `error=msg`, sha of the file) plus `unknown_classification("Not processed.")`;
`on_progress()` is called in a `finally` for every file (drives the UI progress bar). `UserError` (missing key) propagates.

## backend/app/finance.py
SQLite table `claims(id TEXT PK, created_at TEXT, employee_id, employee_name, grade, claimed_inr REAL, eligible_inr REAL, status TEXT DEFAULT 'submitted', payload TEXT)`.
`submit_claim(db, claim, now=None)`: only `ClaimState.READY` else `NotSubmittable(ValueError)`; reference `RMB-<YYYYMMDD>-<count+1 zero-padded to 4>`; payload = `claim.model_dump_json()`;
returns `{id, created_at (ISO seconds), eligible_inr}`. `list_claims(db)` newest first (without payload); `get_claim(db, id)` with parsed payload or `None`. The DB folder is created on demand.

## backend/app/state.py
`Session`: `id, dir, files{name→Path}, extracted[], classifications{}, inputs: ClaimInputs, claim, status (idle|processing|ready|error), done, total, error, submitted_ref, chat_history[], task`.
`AppState(settings=None, *, runtime_dir=None, today=None)`: `runtime = ROOT/backend/runtime`, `policy_dir = runtime/policies` (a **runtime copy** of `data/policies/*.md`, so UI edits never touch the originals),
`uploads = runtime/uploads`, `db_path = runtime/finance.sqlite`; loads the employee; `reset_policy_files()` copies the originals back and clears the cached policy.
`policy()` (async, locked) loads/interprets once; `reload_policy()` re-interprets (cache by document hash) and **rebuilds every session's claim with the existing classifications** (fast; no per-receipt LLM calls).
`store_file(session, name, data)`: `Path(name).name`, de-duplicates names as `stem_2.ext`, writes to the session dir. `process(session, names, use_cache=False)`: sets status `processing`, `total += len(names)`,
runs `process_files` (with `use_extraction_cache=True` when `use_cache`), extends `extracted/classifications`, rebuilds the claim, status `ready`; **a `UserError` (no API key / provider not configured) → status `error` with `"The AI model is not configured: <msg[:200]>"`; any other exception → status `error` with `"<Type>: <msg[:300]>"`** (never a silent hang).
`apply_answer(session, kind, target, value)` kinds: `purpose_group, purpose_item, justification, category, vendor, date, amount, currency, confirm, not_duplicate`; validates group id / receipt name / category ∈ policy ids / ISO date / float,
raising `ValueError` (→ HTTP 422); then rebuilds. `snapshot(session)` → JSON-ready dict (see `06`). `today` is `AppState.today or date.today()`.

## backend/app/chat.py
`ChatDeps(app, session)`. `summarise(claim)` text: state line, counts, open questions (`- [kind] target=...: text`) or "No open questions.", groups. `_resolve(session, text)` matches a receipt by exact/partial file name, then by vendor substring;
ambiguous → message `"'<text>' matches several receipts: a, b. Which one?"`; none → `"No receipt matches '<text>'. Receipts: ..."`. `describe_item(item)` prints file, vendor, date, claimed/eligible, status, category + source + reasoning, decision
explanation, one `Clause <ref> (<doc>): "<quote>"` line per cite, needs, extra reasons.
Agent (`retries=2`, `defer_model_check=True`, deps `ChatDeps`) tools: `claim_status()`, `explain_item(receipt)`, `search_policy(query)` (BM25 over the **runtime** policy documents, top 3 as `"<ref> (<doc>, <heading>): <text>"`),
`record_answer(kind, target, value="")` (resolves receipt names, calls `app.apply_answer`, returns `"Recorded.\n" + summary` or `"Could not record that: <msg>"`). Dynamic instructions add the employee line.
`run_chat(app, session, message)`: lazily builds `app.chat_agent`, ensures the policy is loaded, runs with `message_history=session.chat_history`, stores `result.all_messages()`, returns `result.output`.

## backend/app/main.py
`create_app(state=None)` builds the FastAPI app (lifespan creates `AppState(today=_env_today())` unless one is injected); module-level `app = create_app()`. Limits: `MAX_FILES = 40`, `MAX_BYTES = 10 MB`.
`_env_today()` parses `CLAIM_TODAY`. Static files: if `frontend/` exists, `app.mount("/", StaticFiles(directory=FRONTEND, html=True))` **after** all API routes. Endpoint list, status codes and examples: `06`.

## tools/
* `generate_receipts.py` — deterministic generator (details and the 24-receipt table in `03`). Writes `data/synthetic/receipts/*` (wipes the folder first) and `data/synthetic/ground_truth.json`.
* `extract_receipts.py` — CLI: extraction only + per-field accuracy vs ground truth (`--limit`, `--model`, explicit files); one agent for all files; failures counted as wrong; catches `ModelAPIError`/`httpx2.TransportError` per file and `UserError` globally.
* `run_pipeline.py` — CLI: policy → process all receipts → claim; prints the 24-row table, questions, accuracy block, and writes `data/eval/<model slug>.json` (flags `--model --policy-dir --limit --today`).
* `make_deck.py` — builds the 10-slide deck with python-pptx (optional).

## frontend/index.html
One page, plain JS, no framework, no build. Behaviour in `06`. Security rule: `el()` helper builds DOM nodes; it throws if given an `html` attribute; never use `innerHTML` with dynamic text.

## backend/tests/factories.py (test helper, not a test)
`make_state(tmp_path, policy=POLICY)` → an `AppState` using the real settings, a temp runtime folder, `today = 2026-10-09` (`test_claim.TODAY`) and the **hand-written fixture policy preloaded** (`state._policy = policy`) so no test needs the LLM or the policy cache.
`truth_for(*prefixes)` → ground-truth `ExtractedReceipt`s and `Classification`s for synthetic receipts whose file name starts with a prefix (e.g. `"r05"`). `session_with(state, *prefixes)` → a ready session holding those receipts with a built claim.
Used by `test_state.py`, `test_chat_helpers.py`, `test_api_upload_and_errors.py`.

## Quality tooling
`pyproject.toml`: ruff, line length 120, target py311, rules `E,F,W,I,B,UP`; `E501` ignored in `backend/tests/*` (verbatim policy quotes), bugbear told that `fastapi.File` is an immutable default, isort first-party `app`. Code is formatted with `ruff format`.
`backend/tests/test_api.py` skips (does not fail) when the AI caches are cold for the configured `LLM_MODEL` (`caches_are_warm()` checks the extraction, policy and classification cache folders for `*.json`).
CI (`.github/workflows/ci.yml`): Python 3.12, `pip install -r backend/requirements-dev.txt`, `ruff check backend tools`, then in `backend/`: `pytest -q --cov=app --cov-report=term-missing --cov-fail-under=95` with `ANTHROPIC_API_KEY=ci-dummy-key` (tests never call an LLM; the committed `data/cache` supplies AI results).
Docker: `python:3.12-slim`, installs `backend/requirements.txt`, copies `backend frontend data tools`, runs as a non-root user, `WORKDIR /app/backend`, `uvicorn app.main:app --host 0.0.0.0 --port 8000`, health check on `/api/health`; compose maps port 8000, reads `.env`, sets `CLAIM_TODAY`, and mounts a named volume at `/app/backend/runtime`.
