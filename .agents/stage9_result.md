# Stage 9 — Quality Gates Report

**Date:** 2025-07-14  
**Backend dir:** `c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend`  
**Venv python:** `.\venv\Scripts\python.exe`

---

## Gate 1 — Tests + Coverage

**Command:**
```
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro\backend
& '.\venv\Scripts\python.exe' -m pytest -q --cov=app --cov-report=term-missing
```

**Result:** ✅ PASS

```
133 passed in 9.06s
```

**Coverage table:**

| Name                        | Stmts | Miss | Cover | Missing |
|-----------------------------|-------|------|-------|---------|
| app\__init__.py             | 0     | 0    | 100%  |         |
| app\chat.py                 | 90    | 0    | 100%  |         |
| app\claim.py                | 212   | 0    | 100%  |         |
| app\classifier.py           | 63    | 0    | 100%  |         |
| app\config.py               | 21    | 0    | 100%  |         |
| app\currency.py             | 7     | 0    | 100%  |         |
| app\duplicates.py           | 54    | 0    | 100%  |         |
| app\extraction.py           | 65    | 0    | 100%  |         |
| app\finance.py              | 36    | 0    | 100%  |         |
| app\grouping.py             | 24    | 0    | 100%  |         |
| app\ingest.py               | 54    | 0    | 100%  |         |
| app\main.py                 | 177   | 0    | 100%  |         |
| app\models.py               | 40    | 0    | 100%  |         |
| app\pipeline.py             | 32    | 0    | 100%  |         |
| app\policy\__init__.py      | 0     | 0    | 100%  |         |
| app\policy\clauses.py       | 73    | 0    | 100%  |         |
| app\policy\evaluator.py     | 89    | 0    | 100%  |         |
| app\policy\interpreter.py   | 93    | 0    | 100%  |         |
| app\policy\schema.py        | 79    | 0    | 100%  |         |
| app\quality.py              | 29    | 0    | 100%  |         |
| app\state.py                | 142   | 0    | 100%  |         |
| **TOTAL**                   | **1380** | **0** | **100%** | |

- **Passed:** 133 (expected 133) ✅
- **Failed:** 0
- **Skipped:** 0
- **Coverage:** 100% (expected 100%) ✅

---

## Gate 2 — Ruff Lint

**Command:**
```
cd c:\Users\shiva\Projects\AI-Challenge-with-Kiro
& '.\backend\venv\Scripts\ruff.exe' check backend tools
```

**Result:** ✅ PASS

```
All checks passed!
```

No lint errors. No fixes required.

---

## Gate 3 — Ruff Format Check

**Command:**
```
& '.\backend\venv\Scripts\ruff.exe' format --check backend tools
```

**Result:** ✅ PASS

```
42 files already formatted
```

All 42 files are already correctly formatted. No reformatting needed.

---

## Fixes Applied

None — all gates passed on first run without any changes.

---

## Final Verdict

| Gate                | Expected              | Actual               | Status  |
|---------------------|-----------------------|----------------------|---------|
| Tests               | 133 passed            | 133 passed           | ✅ PASS |
| Coverage            | 100%                  | 100%                 | ✅ PASS |
| Ruff lint           | All checks passed!    | All checks passed!   | ✅ PASS |
| Ruff format         | All files formatted   | 42 files formatted   | ✅ PASS |

**All quality gates passed. No issues found.**
