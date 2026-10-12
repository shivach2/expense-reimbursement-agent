# Stage A1 Result — backend/app files

## Status: COMPLETE

All files from `A1_SOURCE_backend_app(1).md` were created verbatim.

## Files Created

| File | Notes |
|------|-------|
| `backend/app/__init__.py` | Empty file |
| `backend/app/config.py` | 35 lines — runtime settings via dotenv |
| `backend/app/models.py` | 64 lines — Pydantic schemas for receipt extraction |
| `backend/app/currency.py` | 21 lines — static FX rates to INR |
| `backend/app/ingest.py` | 78 lines — image/PDF loading and normalisation |
| `backend/app/quality.py` | 41 lines — deterministic post-extraction checks |
| `backend/app/extraction.py` | 137 lines — vision-LLM receipt extraction via Pydantic AI |
| `backend/app/duplicates.py` | 83 lines — duplicate receipt detection |
| `backend/app/grouping.py` | 34 lines — group expenses into trips by date proximity |
| `backend/app/policy/__init__.py` | Empty file |
| `backend/app/policy/schema.py` | 129 lines — structured policy constraint models |
| `backend/app/policy/clauses.py` | 124 lines — BM25 clause retrieval (RAG) |
| `backend/app/policy/interpreter.py` | 167 lines — LLM policy interpreter with grounding checks |
| `backend/app/policy/evaluator.py` | 191 lines — deterministic policy enforcement |
| `backend/app/classifier.py` | 135 lines — AI expense classification |
| `backend/app/claim.py` | 374 lines — claim assembly with questions and totals |
| `backend/app/pipeline.py` | 59 lines — batch extract+classify pipeline |
| `backend/app/finance.py` | 81 lines — mock SQLite finance system |
| `backend/app/state.py` | 200 lines — in-memory app state and session management |
| `backend/app/chat.py` | 170 lines — conversational assistant with tool calls |
| `backend/app/main.py` | 223 lines — FastAPI app with all API routes |

## Issues

None. All 21 files created successfully with verbatim content from the source document.
