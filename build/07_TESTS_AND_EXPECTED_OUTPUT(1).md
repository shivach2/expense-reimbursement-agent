# 07 — Tests and expected output

## 1. The suite: 133 tests (+ one helper module), run from `backend/` with `python -m pytest -q`

Statement coverage of `app/` is **100%** (about 1,380 statements) and the CI gate is **>= 95%**. No test calls a real LLM.

| File | Tests | Needs | Verifies |
|---|---|---|---|
| `test_ingest.py` | 7 | – | downscale + JPEG re-encode, **EXIF stripped**, PDF rasterised, hash equality, unsupported/corrupt files rejected |
| `test_quality.py` | 8 | – | extraction quality reasons (missing fields, low confidence only when present, line-item sums with/without tax, unsupported currency), currency normalisation, `to_inr` |
| `test_extraction.py` | 8 | – (fake models) | structured output normalisation + caching, FX conversion, **cache hit skips the LLM**, persistent invalid output → error result (not cached), **file name never sent to the model**, 429 retried, **daily-quota 429 not retried**, non-retryable errors propagate |
| `test_duplicates.py` | 8 | – | identical file, same vendor/date/amount, vendor spelling tolerance, different amount/date/currency not duplicates, different bill numbers kept, same bill number confirms, missing fields never match, exempt files |
| `test_grouping.py` | 1 | – | gap splitting, titles, ids |
| `test_policy_evaluator.py` | 15 | – | the deterministic enforcement rules; contains the **hand-written `POLICY` fixture** (`make_policy(hotel_cap)`), `EMP`, helper `ev(...)` that other test files import |
| `test_policy_interpreter.py` | 11 | `data/policies/*.md` | fixture is verbatim-grounded in the real documents; each hallucination kind is caught; LLM retry loop; cache by document hash and re-interpretation on change; multi-document merge and "known categories" hint; clause parsing counts (TEP 13 clauses, GE 6); BM25 retrieval |
| `test_classifier.py` | 6 | – (fake models) | classification, cache, prompt contents (eligibility labels), retry on unknown category id, fallback to `unknown`, unreadable skips LLM |
| `test_claim.py` | 12 | `data/synthetic/ground_truth.json` (run the generator first) | end-to-end claim logic over the 24 synthetic receipts using ground truth as a perfect extractor/classifier |
| `test_finance.py` | 4 | `ground_truth.json` | SQLite submission, references, not-ready refusal |
| `factories.py` | – | – | helper (not a test): `make_state`, `truth_for`, `session_with` (see `04_...`) |
| `test_state.py` | 15 | – | every answer kind, validation errors, name collisions, processing errors incl. missing API key, snapshot, reload recomputes claims |
| `test_chat_helpers.py` | 6 | – | chat tools with a scripted fake model: no receipts, search, record-answer validation, explain with clauses, lazy agent and history, summaries/resolution |
| `test_edge_cases.py` | 10 | – | evaluator gaps (no entitlement, no limit, partial monthly limit exhausted), low-confidence confirm, unsupported currency, wrapped clauses, prompt contents, call delay + cache miss, pipeline failure isolation |
| `test_api_upload_and_errors.py` | 14 | – (fake pipeline) | upload success, name collisions, file-count/size limits, refusals while processing/after submit, unreadable thumbnail, AI-failure mapping (503/502), policy failure + restore, health, `CLAIM_TODAY` |
| `test_api.py` | 8 | **warm caches** (see below) | demo flow, thumbnails + path traversal, answer→submit→finance, bad inputs, **policy edit changes the claim**, scripted chat agent, chat needs receipts |

Test files import each other: `test_policy_interpreter`, `test_claim`, `test_finance`, `test_classifier`, `test_edge_cases`, `factories` import `POLICY/EMP/make_policy/ev` from
`test_policy_evaluator`; `test_finance` and `factories` import `TODAY, load` from `test_claim`; `test_edge_cases` imports `GOOD` from `test_extraction`. Do not rename or move them.

### `test_api.py` depends on warm caches (important)
All 8 tests use the `client` fixture, which **skips** them (message: *AI caches are cold for this LLM_MODEL; run `python tools/run_pipeline.py --today 2026-10-12` once*) unless
`data/cache/extractions/<model>/`, `data/cache/policy/<model>/` and `data/cache/classification/<model>/` contain JSON files for the configured `LLM_MODEL`. On a fresh machine run the warm-up once (Stage 7).
The policy-edit test additionally re-interprets the **edited** policy (hotel 5,000 → 7,000), which is not in a fresh cache, so it makes **one live LLM call (about 10–20 s)** the first time and is cached afterwards.
Expected values in these tests came from a Claude Sonnet 5.5 run: `duplicates == 3`, hotel `r03` decision `partial` citing `TEP-2.1`, after the 7,000 edit `r19` becomes `approved` and the eligible total increases, and the
claim reaches `ready` after answering all questions. A different model may judge a category differently; if a cache-dependent assertion fails, compare with the pipeline output, confirm the difference is a reasonable
LLM judgement, and report it instead of weakening tests silently.
To prove the demo path makes **no** LLM calls once warm: `ANTHROPIC_API_KEY=invalid-dummy-key python -m pytest -q tests/test_api.py`.

## 2. Cumulative expected counts per stage

| After stage | Command (from `backend/`) | Expected |
|---|---|---|
| 2 | `python -m pytest -q tests/test_ingest.py tests/test_quality.py tests/test_extraction.py` | `23 passed` |
| 3 | add `tests/test_duplicates.py tests/test_grouping.py` | `32 passed` |
| 4 | add `tests/test_policy_evaluator.py tests/test_policy_interpreter.py` | `58 passed` |
| 5 | add `tests/test_classifier.py tests/test_claim.py` | `76 passed` |
| 6 | whole suite (all test files created, caches still cold) | `125 passed, 8 skipped` |
| 7 | whole suite after the warm-up | `133 passed` (plus ~16 harmless warnings from PyMuPDF/SWIG and unclosed-sqlite ResourceWarnings in Pillow's EXIF path) |
| 9 | `python -m pytest -q --cov=app` | `133 passed`, `TOTAL ... 100%` |

## 3. Expected output of `python tools/run_pipeline.py --today 2026-10-12`

Deterministic facts (independent of LLM wording): 24 receipts; duplicates `r21, r22, r23`; ineligible includes `r12` (224 days old) and `r24` (personal expense);
`r10` needs a date; hotel bills `r03`/`r19` are `partial` at INR 5,000; the USD receipt `r08` converts to INR 2,016.90. LLM-dependent: categories (23/24 matched ground truth
with Claude Sonnet 5.5; the miss was `r11`, a 4-person tasting menu classed `client_entertainment`), classification confidence, and the wording of reasoning.

The block below is the **real output captured from the finished project** (claim built offline from the cached Claude results, today = 2026-10-12).

### Captured output (claim table, questions, JSON examples, interpreted policy)

```text
file                      category             status         claimed  eligible  note
r01_cafe.png              meals                missing_info    430.50    430.50  Business purpose needed
r02_taxi.png              local_transport      missing_info    640.00    640.00  Business purpose needed
r03_hotel.pdf             lodging              missing_info  7,168.00  5,000.00  The bill is INR 7,168 but the limit is INR 5,000 per night x
r04_dinner_photo.png      meals                missing_info    787.50    787.50  Business purpose needed
r05_stationery.png        office_supplies      missing_info    424.80    424.80  Business purpose needed
r06_blurry_lunch.png      meals                missing_info    546.00    546.00  Business purpose needed
r07_crumpled_fuel.png     fuel                 missing_info  2,100.00  2,100.00  Business purpose needed
r08_foreign_usd.png       meals                questionable  2,016.90      0.00  The bill is INR 2,016.90, above the INR 1,500 per receipt li
r09_foreign_sgd.pdf       local_transport      missing_info  2,162.56  2,162.56  Business purpose needed
r10_missing_date.png      office_supplies      missing_info    268.80      0.00  Missing date
r11_overlimit_meal.png    client_entertainment ineligible   12,980.00      0.00  The bill is INR 12,980, above the INR 3,000 per receipt limi
r12_old_receipt.png       meals                ineligible      682.50      0.00  The receipt is 224 days old; the limit is 60 days. Policy TE
r13_parking.png           local_transport      missing_info    120.00    120.00  Business purpose needed
r14_conf_fee.pdf          training             questionable 11,210.00      0.00  Training needs prior approval before it can be reimbursed. P
r15_train.png             local_transport      missing_info  1,312.50  1,312.50  Business purpose needed
r16_internet.pdf          communication        missing_info  1,178.82  1,178.82  Business purpose needed
r17_taxi2.png             local_transport      missing_info    410.00    410.00  Business purpose needed
r18_lunch_client.png      client_entertainment missing_info  2,772.00  2,772.00  Business purpose needed
r19_hotel2.png            lodging              missing_info  6,496.00  5,000.00  The bill is INR 6,496 but the limit is INR 5,000 per night x
r20_coffee2.png           meals                missing_info    168.00    168.00  Business purpose needed
r21_dup_exact_cafe.png    meals                duplicate       430.50      0.00  Duplicate of r01_cafe.png (identical file); left out of the 
r22_dup_photo_dinner.png  meals                duplicate       787.50      0.00  Duplicate of r04_dinner_photo.png (same vendor, date and amo
r23_dup_taxi_photo.png    local_transport      duplicate       640.00      0.00  Duplicate of r02_taxi.png (same vendor, date and amount); le
r24_pharmacy.png          personal_expenses    ineligible      448.00      0.00  Personal expenses is not reimbursable: Personal expenses, me

state=needs_input claimed=40212.38 eligible=23052.68 counts={'missing_info': 16, 'questionable': 2, 'ineligible': 3, 'duplicate': 3}
eligible_by_category= {"meals": 1932.0, "local_transport": 4645.06, "lodging": 10000.0, "office_supplies": 424.8, "fuel": 2100.0, "training": 0.0, "communication": 1178.82, "client_entertainment": 2772.0}
groups= [('g-2026-09-01', 'Expenses on 01 Sep 2026', 1, 1178.82), ('g-2026-09-14', 'Expenses 14 Sep – 24 Sep 2026', 16, 21873.86)]

5 questions:
  [justify] target=r08_foreign_usd.png
      HARBOR GRILL: The bill is INR 2,016.90, above the INR 1,500 per receipt limit. It can be reimbursed only as an approved exception. Policy TEP-3.1: "Meals during business travel are reimbursable up to INR 1,500 per receipt." Please provide manager-approved justification.
  [field] target=r10_missing_date.png
      CORNER STATIONERS: please provide the date.
  [justify] target=r14_conf_fee.pdf
      NOVATECH SUMMIT: Training needs prior approval before it can be reimbursed. Policy TEP-6.1: "Training courses and conference fees are reimbursable up to INR 15,000 per receipt, and require prior written approval from the employee's manager." Please provide approval reference or justification.
  [purpose] target=g-2026-09-14
      What was the business purpose of these 16 receipt(s)? (Expenses 14 Sep – 24 Sep 2026)
  [purpose] target=g-2026-09-01
      What was the business purpose of these 1 receipt(s)? (Expenses on 01 Sep 2026)

--- classification reasoning examples ---
r03_hotel.pdf => lodging | The bill is from a hotel for one night's room stay plus breakfast, which is part of the hotel folio. The total above the line items (7168 vs 6400) is normal tax, so this fits lodging. | conf 0.9
r07_crumpled_fuel.png => fuel | The receipt is from a fuel station for 20L of petrol, which is a fuel expense and is available to your grade. | conf 0.97
r24_pharmacy.png => personal_expenses | The bill is from a pharmacy for cough syrup and vitamins, which are personal medical items. These fall under personal expenses, which the policy does not reimburse. | conf 0.97
r11_overlimit_meal.png => client_entertainment | A tasting menu for four with wine at a fine-dining restaurant looks like hosted entertainment rather than a personal meal. The total of 12,980 INR is the 11,000 subtotal plus 1,980 tax, so the amount is consistent. | conf 0.6

--- one claim item JSON (hotel) ---
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

--- one extraction JSON (r08 usd) ---
{
  "source_file": "r08_foreign_usd.png",
  "file_sha256": "e25ffb37f81cd6e52e8483c8544610e1caba3a6759002beca992f54ec53fee4b",
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
}

--- policy summary ---
LIMIT grade_entitlements.md:3.1 cat=communication amt=800.0 INR per_month action=partial grades=['E1', 'E2', 'E3'] approval=False
   quote='Mobile and broadband bills are reimbursable up to INR 800 per month for Executive grades.'
LIMIT grade_entitlements.md:3.2 cat=communication amt=1200.0 INR per_month action=partial grades=['M1', 'M2', 'M3', 'D1', 'D2', 'D3'] approval=False
   quote='Mobile and broadband bills are reimbursable up to INR 1,200 per month for Manager and Director grades.'
LIMIT travel_expense_policy.md:2.1 cat=lodging amt=5000.0 INR per_night action=partial grades=None approval=False
   quote='Hotel accommodation is reimbursable up to INR 5,000 per night.'
LIMIT travel_expense_policy.md:3.1 cat=meals amt=1500.0 INR per_receipt action=needs_approval grades=None approval=False
   quote='Meals during business travel are reimbursable up to INR 1,500 per receipt.'
LIMIT travel_expense_policy.md:4.1 cat=local_transport amt=3000.0 INR per_day action=reject grades=None approval=False
   quote='Local taxi, cab, parking and public transport are reimbursable up to INR 3,000 per day.'
LIMIT travel_expense_policy.md:4.2 cat=fuel amt=2500.0 INR per_receipt action=reject grades=None approval=False
   quote='Fuel for a personal vehicle used on official duty is reimbursable up to INR 2,500 per receipt.'
LIMIT travel_expense_policy.md:5.1 cat=client_entertainment amt=3000.0 INR per_receipt action=reject grades=None approval=False
   quote='Meals and entertainment for clients are reimbursable up to INR 3,000 per receipt.'
LIMIT travel_expense_policy.md:6.1 cat=training amt=15000.0 INR per_receipt action=reject grades=None approval=True
   quote="Training courses and conference fees are reimbursable up to INR 15,000 per receipt, and require prior written approval from the employee's manager."
LIMIT travel_expense_policy.md:7.1 cat=office_supplies amt=1000.0 INR per_receipt action=reject grades=None approval=False
   quote='Office supplies are reimbursable up to INR 1,000 per receipt.'
EXCL 1.3 personal_expenses | Personal expenses, medical expenses, fines and penalties are not reimbursable under any circumstances. | Personal expenses, medical expenses, fines and penalties are not reimbursable under any circumstances.
AGE 1.1 60 Expense receipts must be submitted within 60 days of the date of the expense.
categories: [('meals', 'Meals'), ('local_transport', 'Local transport'), ('fuel', 'Fuel'), ('communication', 'Communication'), ('office_supplies', 'Office supplies'), ('training', 'Training'), ('lodging', 'Lodging'), ('client_entertainment', 'Client entertainment'), ('personal_expenses', 'Personal expenses')]
M2 eligible: ['client_entertainment', 'communication', 'fuel', 'local_transport', 'lodging', 'meals', 'office_supplies', 'training']
E1 eligible: ['communication', 'fuel', 'local_transport', 'meals', 'office_supplies', 'training']
ENT grade_entitlements.md 2.1 meals ['E1', 'E2', 'E3', 'M1', 'M2', 'M3', 'D1', 'D2', 'D3']
ENT grade_entitlements.md 2.1 local_transport ['E1', 'E2', 'E3', 'M1', 'M2', 'M3', 'D1', 'D2', 'D3']
ENT grade_entitlements.md 2.1 fuel ['E1', 'E2', 'E3', 'M1', 'M2', 'M3', 'D1', 'D2', 'D3']
```

Accuracy block printed by `tools/run_pipeline.py` for the same run (Claude Sonnet 5.5, 24 receipts):

```
accuracy vs ground truth
  extraction vendor    24/24 (100%)
  extraction date      24/24 (100%)
  extraction total     24/24 (100%)
  extraction currency  24/24 (100%)
  classification     23/24 (96%)
  duplicates found   3/3 (100%), false alarms 0
  ineligible found   2/2 (100%), false alarms 1
```
(`false alarms 1` = `r11`, the tasting menu classed as client entertainment and rejected because 12,980 exceeds the 3,000 limit.)

## All 133 test ids (to check you recreated every test)

```
tests/test_api.py::test_demo_receipts_become_a_claim_with_decisions
tests/test_api.py::test_thumbnails_are_served_for_images_and_pdfs
tests/test_api.py::test_answering_then_submitting_reaches_the_mock_finance_system
tests/test_api.py::test_bad_inputs_are_rejected
tests/test_api.py::test_editing_the_policy_document_changes_the_claim_without_code
tests/test_api.py::test_unknown_policy_document_is_404
tests/test_api.py::test_chat_agent_explains_with_clauses_and_records_answers
tests/test_api.py::test_chat_needs_receipts_first
tests/test_api_upload_and_errors.py::test_upload_processes_files_and_builds_a_claim
tests/test_api_upload_and_errors.py::test_uploading_the_same_name_twice_keeps_both_files
tests/test_api_upload_and_errors.py::test_too_many_files_are_rejected
tests/test_api_upload_and_errors.py::test_oversized_file_is_rejected
tests/test_api_upload_and_errors.py::test_upload_and_demo_are_refused_while_processing
tests/test_api_upload_and_errors.py::test_upload_is_refused_after_submission
tests/test_api_upload_and_errors.py::test_thumbnail_of_an_unreadable_file_is_415
tests/test_api_upload_and_errors.py::test_submitting_an_empty_session_is_409
tests/test_api_upload_and_errors.py::test_chat_ai_failures_map_to_http_errors
tests/test_api_upload_and_errors.py::test_policy_view_failures_are_reported
tests/test_api_upload_and_errors.py::test_failed_policy_edit_restores_the_previous_text
tests/test_api_upload_and_errors.py::test_failed_policy_reset_is_reported
tests/test_api_upload_and_errors.py::test_unknown_finance_claim_is_404_and_health_reports_the_model
tests/test_api_upload_and_errors.py::test_claim_today_is_read_from_the_environment
tests/test_chat_helpers.py::test_tools_before_any_receipts_give_helpful_answers
tests/test_chat_helpers.py::test_search_policy_returns_clause_references
tests/test_chat_helpers.py::test_record_answer_validation_messages_and_success
tests/test_chat_helpers.py::test_explain_item_lists_clause_and_what_is_needed
tests/test_chat_helpers.py::test_run_chat_builds_the_agent_lazily_and_keeps_history
tests/test_chat_helpers.py::test_summary_and_receipt_resolution
tests/test_claim.py::test_first_pass_finds_every_planted_problem
tests/test_claim.py::test_ineligible_items_carry_the_clause_that_rejected_them
tests/test_claim.py::test_hotels_are_partially_reimbursed_up_to_the_policy_limit
tests/test_claim.py::test_questions_are_minimal
tests/test_claim.py::test_excluded_and_duplicates_do_not_count
tests/test_claim.py::test_foreign_currency_converted
tests/test_claim.py::test_answering_the_questions_makes_the_claim_ready
tests/test_claim.py::test_changing_the_policy_changes_the_outcome_without_code_changes
tests/test_claim.py::test_ambiguous_category_asks_the_employee_and_their_choice_wins
tests/test_claim.py::test_not_duplicate_override_keeps_the_receipt
tests/test_claim.py::test_all_unusable_receipts_block_the_claim
tests/test_claim.py::test_failed_extraction_asks_for_manual_entry
tests/test_classifier.py::test_classifies_into_a_policy_category_and_caches
tests/test_classifier.py::test_prompt_lists_policy_categories_and_grade_eligibility
tests/test_classifier.py::test_unknown_category_is_sent_back_to_the_model
tests/test_classifier.py::test_persistently_invalid_output_falls_back_to_unknown
tests/test_classifier.py::test_unreadable_receipt_skips_the_llm
tests/test_classifier.py::test_category_description_marks_exclusions
tests/test_duplicates.py::test_identical_file_is_duplicate_even_without_extracted_fields
tests/test_duplicates.py::test_same_vendor_date_amount_is_duplicate
tests/test_duplicates.py::test_vendor_spelling_variation_still_matches
tests/test_duplicates.py::test_different_amount_or_date_is_not_duplicate
tests/test_duplicates.py::test_two_real_purchases_with_different_bill_numbers_are_kept
tests/test_duplicates.py::test_same_bill_number_confirms_duplicate
tests/test_duplicates.py::test_missing_fields_never_match_semantically
tests/test_duplicates.py::test_exempt_item_is_kept_but_still_serves_as_original
tests/test_edge_cases.py::test_category_without_any_entitlement_is_rejected
tests/test_edge_cases.py::test_category_without_a_limit_is_approved_in_full
tests/test_edge_cases.py::test_partial_monthly_limit_is_consumed_across_receipts
tests/test_edge_cases.py::test_low_confidence_extraction_asks_for_confirmation_until_confirmed
tests/test_edge_cases.py::test_unsupported_currency_asks_for_an_inr_amount
tests/test_edge_cases.py::test_different_vendors_with_same_date_and_amount_are_not_duplicates
tests/test_edge_cases.py::test_wrapped_clause_lines_are_joined
tests/test_edge_cases.py::test_pdf_text_is_added_to_the_prompt_but_the_file_name_never_is
tests/test_edge_cases.py::test_call_delay_is_applied_and_a_cache_miss_falls_through_to_the_llm
tests/test_edge_cases.py::test_failures_become_failed_items_and_progress_is_reported
tests/test_extraction.py::test_successful_extraction_normalises_and_caches
tests/test_extraction.py::test_foreign_currency_converted
tests/test_extraction.py::test_cache_hit_skips_the_llm
tests/test_extraction.py::test_persistent_invalid_output_returns_error_result
tests/test_extraction.py::test_file_name_is_not_sent_to_the_model
tests/test_extraction.py::test_rate_limit_is_retried
tests/test_extraction.py::test_daily_quota_is_not_retried
tests/test_extraction.py::test_non_retryable_http_error_propagates
tests/test_finance.py::test_ready_claim_is_stored_and_retrievable
tests/test_finance.py::test_references_increment
tests/test_finance.py::test_claim_that_is_not_ready_is_refused
tests/test_finance.py::test_unknown_claim_returns_none
tests/test_grouping.py::test_grouping_splits_on_gap_and_titles_ranges
tests/test_ingest.py::test_image_is_downscaled_and_reencoded_as_jpeg
tests/test_ingest.py::test_exif_metadata_is_stripped
tests/test_ingest.py::test_pdf_is_rasterised
tests/test_ingest.py::test_same_bytes_same_hash
tests/test_ingest.py::test_unsupported_extension_rejected
tests/test_ingest.py::test_corrupt_image_rejected
tests/test_ingest.py::test_corrupt_pdf_rejected
tests/test_policy_evaluator.py::test_hotel_over_cap_is_partially_reimbursed_with_clause_and_quote
tests/test_policy_evaluator.py::test_hotel_within_cap_and_multi_night
tests/test_policy_evaluator.py::test_policy_change_applies_without_code_change
tests/test_policy_evaluator.py::test_meals_over_cap_needs_exception_then_approved_with_justification
tests/test_policy_evaluator.py::test_excluded_category_rejected_with_clause
tests/test_policy_evaluator.py::test_grade_not_entitled
tests/test_policy_evaluator.py::test_receipt_age_limit_boundary
tests/test_policy_evaluator.py::test_missing_date_skips_age_check
tests/test_policy_evaluator.py::test_per_day_limit_is_shared_across_receipts_on_same_day
tests/test_policy_evaluator.py::test_grade_specific_limit_beats_general_and_is_monthly
tests/test_policy_evaluator.py::test_training_requires_prior_approval_even_under_limit
tests/test_policy_evaluator.py::test_unknown_category_is_flagged_for_clarification
tests/test_policy_evaluator.py::test_eligible_categories_depend_on_grade
tests/test_policy_evaluator.py::test_tiny_amounts_are_fine[0.0]
tests/test_policy_evaluator.py::test_tiny_amounts_are_fine[0.01]
tests/test_policy_interpreter.py::test_fixture_is_verbatim_grounded_in_real_documents[travel_expense_policy.md]
tests/test_policy_interpreter.py::test_fixture_is_verbatim_grounded_in_real_documents[grade_entitlements.md]
tests/test_policy_interpreter.py::test_grounding_catches_each_kind_of_hallucination
tests/test_policy_interpreter.py::test_quote_matching_ignores_whitespace_and_case
tests/test_policy_interpreter.py::test_model_is_retried_until_output_is_grounded
tests/test_policy_interpreter.py::test_never_grounded_output_raises
tests/test_policy_interpreter.py::test_document_name_is_stamped_by_code_not_the_model
tests/test_policy_interpreter.py::test_result_is_cached_by_document_hash_and_reinterpreted_on_change
tests/test_policy_interpreter.py::test_load_policy_set_merges_documents_and_shares_category_ids
tests/test_policy_interpreter.py::test_clause_parsing_of_real_documents
tests/test_policy_interpreter.py::test_bm25_retrieves_the_relevant_clause
tests/test_quality.py::test_clean_receipt_has_no_reasons
tests/test_quality.py::test_unreadable_short_circuits
tests/test_quality.py::test_missing_fields_reported
tests/test_quality.py::test_low_confidence_flagged_only_when_value_present
tests/test_quality.py::test_line_items_must_sum_to_total_with_or_without_tax
tests/test_quality.py::test_unsupported_currency_flagged
tests/test_quality.py::test_currency_normalised_and_validated
tests/test_quality.py::test_to_inr
tests/test_state.py::test_every_answer_kind_updates_the_claim
tests/test_state.py::test_group_purpose_removes_the_purpose_question
tests/test_state.py::test_invalid_answers_raise_value_errors[bogus-r05_stationery.png-]
tests/test_state.py::test_invalid_answers_raise_value_errors[purpose_group-g-1999-01-01-x]
tests/test_state.py::test_invalid_answers_raise_value_errors[confirm-ghost.png-]
tests/test_state.py::test_invalid_answers_raise_value_errors[date-r05_stationery.png-not-a-date]
tests/test_state.py::test_invalid_answers_raise_value_errors[amount-r05_stationery.png-abc]
tests/test_state.py::test_invalid_answers_raise_value_errors[category-r05_stationery.png-yachts]
tests/test_state.py::test_category_answers_need_a_loaded_policy
tests/test_state.py::test_store_file_avoids_name_collisions
tests/test_state.py::test_processing_errors_are_reported_not_swallowed
tests/test_state.py::test_rebuild_is_a_noop_without_policy_or_receipts
tests/test_state.py::test_snapshot_tolerates_a_missing_classification
tests/test_state.py::test_reloading_the_policy_recomputes_existing_claims
tests/test_state.py::test_a_missing_api_key_is_reported_in_plain_words
```
