# 01 — Product, rules and architecture

## 1. The business problem (from the competition brief)

Employees spend time collecting bills, entering details, categorising expenses, checking what is allowed and
preparing reimbursement claims. The brief asks for an AI-native reimbursement assistant, available over a
familiar interface such as chat, where an employee drops in photographs, PDFs or other bills and the system
does as much of the reimbursement work as possible: understand receipts, extract information, group expenses,
notice missing details, ask only necessary questions, check basic rules, identify possible duplicates, and
prepare a submission-ready claim. The actual corporate reimbursement system may be **mocked**.

The builder added six AI requirements that drive the architecture:

1. **AI-based eligibility identification** – understand which reimbursement categories an employee may claim from
   the employee profile and the policy documents.
2. **Intelligent bill classification and mapping** – understand each expense, pick the category, match it to the
   employee's eligible categories, organise bills into claims, flag ineligible/unclear bills.
3. **AI-powered policy interpretation and validation** – read policy documents dynamically (not hard-coded rules);
   e.g. hotel limit INR 5,000, bill INR 6,000 → flag it, cite the clause, recommend the eligible amount
   (INR 5,000) if the policy allows partial reimbursement.
4. **Automatic adaptation to policy changes** – editing a policy document (limit 5,000 → 7,000) must be enough;
   no hard-coded limits or eligibility conditions anywhere in the application.
5. **Explainable decisions** – why this category, which clause, why accepted/rejected/flagged, what else is
   needed, what amount is eligible, with exact document and section reference.
6. **Reliable execution** – AI extracts structured constraints and determines applicability; **deterministic
   code performs the calculations and enforces the constraints**.

## 2. Competition rules that shaped the build (must be respected in the rebuild)

* Use only **synthetic / dummy / public data**. No Jio/Reliance (or any company) confidential, employee,
  customer, financial or personally identifiable data, no internal documents, no real policies.
* Personal accounts/tools are allowed (own LLM API key, own GitHub) but no company data may be uploaded to them.
* No secrets in the repository. Keys live in a git-ignored `.env`.
* **Deliverables required by the rules** (details in `09_...`): (1) fully functional project by 12 Oct 2026; (2) a **technical design document** with project overview *including the track selected*,
  system architecture diagrams (flow diagrams), setup and deployment instructions, code explanations and assumptions; (3) a **YouTube link** to a demo video showing key features and the user experience;
  (4) all code on a **personal GitHub** with the link shared together with all documents and the video, **without asking for access permissions**; (5) **comprehensive unit tests**; if hosted, the link.
* **Evaluation criteria:** Innovation and creativity · Technical complexity · Code quality · Testing and reliability · Documentation · Demo quality. `docs/EVALUATION_MAPPING.md` maps each to evidence.
* The track chosen: **Track 1 — Expense & Reimbursement Agent**. The "today" for the demo is pinned with `CLAIM_TODAY=2026-10-12`.

## 3. Architecture

```
 receipts (jpg/png/webp/bmp/pdf)                 policy documents (Markdown, numbered clauses "2.1 ...")
        |                                                       |
  [1] ingest.py                                       [3] policy/interpreter.py  (LLM, Pydantic AI)
      - strip EXIF (re-encode JPEG)                         - prompt = whole document + known category ids
      - rasterise PDFs (PyMuPDF, 150 dpi, <=3 pages)        - output_type = PolicyConstraints
      - resize to <=1600 px, sha256 of original bytes       - output_validator: grounding_problems()
        |                                                     -> ModelRetry until every quote is verbatim
  [2] extraction.py (LLM vision, Pydantic AI)                 and every number appears in its quote
      - output_type = Receipt (validated)                   - cached by sha256(document)+known ids
      - retry/backoff for 429/503/connect errors              (+ model name in the cache path)
      - result cached by sha256(file)+model                       |
        |                                                         v
        v                                                   PolicySet (merged constraints of all documents)
  [4] classifier.py (LLM, text-only)  <---------------- eligible categories for the employee's grade
      - picks one policy category id + reasoning                  |
        |                                                         |
        +----------------------> [5] policy/evaluator.py <--------+      [RAG] policy/clauses.py (BM25) is
                                     DETERMINISTIC: entitlement,         used by the chat agent's
                                     exclusion, age, limits, partial,    search_policy tool
                                     approval, per-day/month tracker
                                     -> Decision(outcome, eligible_inr, cites[ref,quote], explanation, needs)
                                          |
  [6] claim.py  DETERMINISTIC: duplicates.py + grouping.py + statuses + minimal questions + claim state
                                          |
  [7] chat.py  AGENT (Pydantic AI + tools): claim_status, explain_item, search_policy, record_answer
                                          |
  [8] main.py (FastAPI) + state.py (sessions) + frontend/index.html (one page) + finance.py (SQLite mock)
```

## 4. Where each technique is used and why (reproduce this reasoning in the README)

| Component | Technique | Why |
|---|---|---|
| Receipt extraction | LLM with vision | Photos/PDFs are messy; OCR rules would be brittle |
| Policy interpretation | LLM + deterministic grounding check | Policies are prose that changes; the check (verbatim quote, number appears in quote, clause exists, category defined) stops hallucinated limits |
| Clause retrieval (RAG) | BM25 over clauses | Two short documents don't justify embeddings or a vector DB; BM25 is offline, free, deterministic; swapping to embeddings would only change `ClauseIndex.search` |
| Bill classification | LLM (text) with the policy's categories in the prompt | A judgement call; must be explained to the user |
| Eligible amount / caps / partial reimbursement / FX | Deterministic Python | Financial accuracy; reproducible; auditable |
| Duplicate detection | Deterministic (file hash + same vendor/date/amount, bill number guard) | Image hashing was **measured and rejected**: on same-template receipts different bills hashed identically and a re-photographed duplicate hashed far apart |
| Grouping, claim state, questions | Deterministic | Auditable, testable |
| Chat | Agent with tools | Open-ended follow-ups; the agent only *reads* decisions and *records* answers; code decides |
| Model access | Pydantic AI, model string from `LLM_MODEL` | Provider-agnostic (Anthropic, Google, OpenAI, ...) |

## 5. Key design decisions (and the reasons — keep them, they avoid known pitfalls)

1. **No LangChain/LangGraph.** The flow is a fixed pipeline; only chat needs an agent loop. Pydantic AI gives typed
   outputs, automatic validation retries and tools with little code.
2. **Policy values appear nowhere in code.** `grep -ri "5,000\|5000"` over `backend/app` must find nothing. The numbers
   (5,000 per night, 1,500 per receipt, 60 days, ...) exist only in `data/policies/*.md` and in cached LLM output.
3. **Grounding check is the reliability backbone.** An interpreted constraint is accepted only if: its clause number exists
   in the document, its quote is a whitespace/case-insensitive substring of that clause text, its category id is
   defined in the same output's `categories`, and (for limits/age rules) its number appears in the quote. Failures are
   returned to the LLM as a `ModelRetry` listing the problems.
4. **Category ids are not hard-coded.** The LLM defines them from the policy (`meals`, `lodging`, ...). Later documents
   are told the ids defined by earlier ones ("reuse them") so documents agree on ids.
5. **Cache by content hash.** Policy interpretation cache key = sha256(document text + known ids); extraction cache key =
   sha256(file bytes) and model; classification cache key includes file hash, policy document hashes, grade, model and
   the classifier instruction text. Changing any input changes the key — this is how "edit the policy and it just
   works" and "demo works offline" both hold.
6. **Questions are minimal.** One business-purpose question per trip group (not per receipt); the classifier may only
   ask for clarification when the choice changes the outcome *and* its confidence is below 0.75; a receipt that is
   already rejected by policy asks nothing; basics (vendor/date/amount) are asked before anything else.
7. **Status semantics are fixed** (see the table below) and every status carries human-readable reasons.
8. **Sessions are in memory; submitted claims go to SQLite** (`backend/runtime/finance.sqlite`, git-ignored).
9. **UI is one HTML file with plain JavaScript, no build step.** All dynamic text is inserted with `textContent` /
   DOM nodes (never `innerHTML`) because vendor names come from model output; the only formatting allowed in chat
   replies is `**bold**`, rendered as `<b>` nodes.
10. **Honest failure handling.** A file that cannot be processed becomes a claim item with status "needs info" and a
    question; the batch never aborts. Daily-quota 429s are *not* retried (waiting won't help); 429/503/connection
    errors otherwise retry with exponential backoff (2, 4, 8, 16, 30 s; 6 attempts).

## 6. Status and outcome vocabulary

Item status (`ItemStatus`): `complete`, `missing_info`, `questionable`, `duplicate`, `ineligible`.
Claim state (`ClaimState`): `ready` (every included item is `complete`), `needs_input` (some included item is not),
`blocked` (no included item: everything is duplicate/ineligible or there are no items).
Decision outcome (`Outcome`): `approved`, `partial`, `flagged` (resolvable: needs justification/approval/category),
`rejected` (cannot be claimed).
Question kinds: `field` (missing vendor/date/amount/currency), `clarify` (category unclear; has `options`),
`purpose` (business purpose for a group), `justify` (approval/justification for a flagged item), `confirm`
(low-confidence extraction).

Mapping: decision `rejected` → item `ineligible`; decision `flagged` → item `questionable` + `justify` question
(or `clarify` when the category is unknown/unclear); decision `partial` → item stays `complete` (with an explanatory
reason) but still needs a business purpose; duplicates → `duplicate`.

## 7. Directory tree to produce

```
<project root>/
  .env.example  .gitignore  .dockerignore  DATA_POLICY.md  README.md  pyproject.toml (ruff)  Dockerfile  docker-compose.yml
  .github/workflows/ci.yml
  backend/
    requirements.txt  requirements-dev.txt  pytest.ini
    app/ __init__.py config.py models.py currency.py ingest.py quality.py extraction.py duplicates.py grouping.py
         classifier.py claim.py pipeline.py state.py finance.py chat.py main.py
         policy/ __init__.py schema.py clauses.py interpreter.py evaluator.py
    tests/ factories.py (helper) test_ingest.py test_quality.py test_extraction.py test_duplicates.py test_grouping.py
           test_policy_evaluator.py test_policy_interpreter.py test_classifier.py test_claim.py test_finance.py
           test_state.py test_chat_helpers.py test_edge_cases.py test_api_upload_and_errors.py test_api.py
  frontend/ index.html
  tools/ generate_receipts.py extract_receipts.py run_pipeline.py make_deck.py
  data/ policies/{travel_expense_policy.md, grade_entitlements.md}  employees/emp_demo_m2.json
        synthetic/ (generated; commit it)   cache/ (generated by the warm-up; commit it)   eval/ (generated)
  docs/ TECHNICAL_DESIGN.md SETUP_AND_DEPLOYMENT.md TEST_REPORT.md EVALUATION_MAPPING.md BUSINESS_IMPACT.md
        DEMO_VIDEO_GUIDE.md DEMO_SCRIPT.md SUBMISSION_CHECKLIST.md  screenshots/ (5 images, captured from the app)
```
Runtime-only (git-ignored): `.env`, `.venv/`, `backend/runtime/` (uploads, SQLite, runtime copy of policies), `submission/`.
