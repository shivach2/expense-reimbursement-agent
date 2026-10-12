# Stage 0 Result

**Status:** Complete  
**Date:** Stage 0 — Scaffold and Configuration Files

## Directories Created

All required directories created under `c:\Users\shiva\Projects\AI-Challenge-with-Kiro`:

```
backend/
backend/app/
backend/app/policy/
backend/tests/
frontend/
tools/
data/
data/policies/
data/employees/
data/synthetic/
data/synthetic/receipts/
data/cache/
data/cache/extractions/
data/cache/policy/
data/cache/classification/
data/eval/
docs/
docs/screenshots/
.github/
.github/workflows/
.agents/
.agents/tasks/
```

## Files Created

### From A4 (configuration, data, CI):
- `.gitignore`
- `.env.example`
- `pyproject.toml`
- `backend/requirements.txt`
- `backend/requirements-dev.txt`
- `backend/pytest.ini`
- `DATA_POLICY.md`
- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `.github/workflows/ci.yml`
- `data/policies/travel_expense_policy.md`
- `data/policies/grade_entitlements.md`
- `data/employees/emp_demo_m2.json`

### From A5 (documentation):
- `README.md`
- `docs/TECHNICAL_DESIGN.md`
- `docs/SETUP_AND_DEPLOYMENT.md`
- `docs/TEST_REPORT.md`
- `docs/EVALUATION_MAPPING.md`
- `docs/BUSINESS_IMPACT.md`
- `docs/DEMO_VIDEO_GUIDE.md`
- `docs/DEMO_SCRIPT.md`
- `docs/SUBMISSION_CHECKLIST.md`

## Virtual Environment

Created at `backend/venv/` using Python 3.13.

## Key Packages Installed (pip list — key packages)

```
fastapi                                  0.143.0
httpx                                    0.28.1
httpx2                                   2.13.1
ImageHash                                4.3.2
pillow                                   12.3.0
pydantic                                 2.14.1
pydantic-ai                              2.54.0
pydantic-ai-slim                         2.54.0
pydantic_core                            2.50.1
pydantic-evals                           2.54.0
pydantic-settings                        2.15.0
pymupdf                                  1.28.2
pytest                                   9.1.1
pytest-cov                               7.1.0
python-dotenv                            1.2.4
python-multipart                         0.0.32
python-pptx                              1.0.2
PyYAML                                   6.0.3
ruff                                     0.17.0
sqlmodel                                 0.0.48
uvicorn                                  0.54.0
```

## Issues / Notes

- None. All packages installed successfully on first attempt.
- `pydantic-ai==2.54.0` was pinned and installed before `requirements-dev.txt` as specified.
- `.env` file NOT created (user must supply their API key).
- `venv/` is inside `backend/` (not `.venv/` at the project root) as the task instructions specified using `backend/venv`.
  Note: The `build_plan.md` references `.venv\Scripts\python.exe` at the project root while the task instructions
  specify `backend/venv`. The venv was created at `backend/venv` per the explicit task instructions.
