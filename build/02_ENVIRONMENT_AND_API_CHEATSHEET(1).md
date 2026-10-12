# 02 — Environment, pinned versions and the Pydantic AI 2.x cheat sheet

## 1. Versions the project was built and tested with

| Package | Version | Notes |
|---|---|---|
| Python | 3.14.7 | 3.11+ should work (uses `StrEnum`, `X \| Y` types, `from __future__ import annotations`) |
| pydantic | 2.14.0 | |
| pydantic-ai (and pydantic-ai-slim) | **2.54.0** | **API differs from 0.x/1.x. Use the cheat sheet below.** |
| fastapi | 0.143.0 | |
| starlette | 1.7.0 | |
| uvicorn | 0.54.0 | `uvicorn[standard]` in requirements |
| python-multipart | 0.0.32 | needed for file uploads |
| pillow | 12.3.0 | needs >= 10.1 (`ImageFont.load_default(size)`) |
| pymupdf | 1.28.2 | import name is `pymupdf` (not `fitz`) |
| imagehash | 4.3.2 | listed in requirements but **unused** by the code |
| sqlmodel | 0.0.48 | listed in requirements but **unused** (SQLite via stdlib `sqlite3`) |
| anthropic | 1.12.1 | pulled in by pydantic-ai |
| google-genai | 2.29.0 | pulled in by pydantic-ai |
| httpx | 0.28.1 | |
| **httpx2** | 2.13.1 | HTTP client used inside Pydantic AI 2.x; its `TransportError` escapes agent runs |
| python-dotenv | 1.2.4 | |
| PyYAML | 6.0.3 | unused now (was for the removed rules file) but harmless |
| pytest | 9.1.1 | |
| pytest-cov (coverage 7.16.2) | 7.1.0 | coverage reports and the CI gate (`backend/requirements-dev.txt`) |
| ruff | 0.17.0 | lint + format (`pyproject.toml`; `backend/requirements-dev.txt`) |
| python-pptx | 1.0.2 | only for `tools/make_deck.py` |

Install exactly with: `pip install -r backend/requirements.txt` (unpinned list in the appendix) and, to be safe,
`pip install "pydantic-ai==2.54.0"` first. If that exact version is unavailable on the other PC's index, install the
closest 2.x release and consult the cheat sheet; report which version you used.

Development tools (tests with coverage, lint, deck): `pip install -r backend/requirements-dev.txt` (it includes `requirements.txt`, `pytest-cov`, `ruff`, `python-pptx`).

## 2. Environment variables (`.env` at the project root)

```
LLM_MODEL=anthropic:claude-sonnet-5-5      # Pydantic AI model string: <provider>:<model>
ANTHROPIC_API_KEY=...                      # only the key for the provider you use
GOOGLE_API_KEY=...
OPENAI_API_KEY=...
LLM_CALL_DELAY_S=0                         # seconds to sleep after each successful extraction (free-tier pacing)
USE_EXTRACTION_CACHE=false                 # true = read cached extraction results instead of calling the LLM
CLAIM_TODAY=2026-10-12                     # optional: pins "today" for the 60-day age rule (read by main.py)
```
`backend/app/config.py` loads `<project root>/.env` with `python-dotenv` (existing process env vars win).
Model strings: `anthropic:claude-sonnet-5-5`, `google:gemini-3.8-flash` (**not** `google-gla:`), `openai:<model>`.

## 3. Pydantic AI 2.54 cheat sheet (verified by actually running the code)

```python
from pydantic_ai import Agent, BinaryContent, ModelRetry, RunContext
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError, UnexpectedModelBehavior, UserError
import httpx2   # transitive dependency of pydantic-ai 2.x
```

* **Create an agent**
  `Agent(model, output_type=PydanticModel, instructions="...", retries=2, deps_type=SomeType, defer_model_check=True)`
  `model` may be a string (`"anthropic:claude-sonnet-5-5"`) or a model object (`FunctionModel(...)`, `TestModel(...)`).
  `defer_model_check=True` means constructing the agent does **not** require an API key; the key is needed on first call.
  Missing key at call time raises `UserError("Set the `ANTHROPIC_API_KEY` environment variable ...")`.
* **Run**: `result = await agent.run(user_prompt, deps=..., message_history=...)`; the typed value is `result.output`;
  full history is `result.all_messages()` (pass it back as `message_history` for multi-turn chat).
* **Multimodal prompt**: `user_prompt` may be a list: `["text", BinaryContent(data=bytes, media_type="image/jpeg")]`.
* **Output validation retry**: decorate with `@agent.output_validator`; a function `(ctx: RunContext[Deps], out) -> out`
  that raises `ModelRetry("message")` makes the framework send the message back to the LLM and retry, up to
  `retries` times, after which `UnexpectedModelBehavior` is raised. Validation errors of the `output_type` model
  (e.g. a field validator raising `ValueError`) are retried the same way.
* **Tools**: `@agent.tool` on an `async def f(ctx: RunContext[Deps], arg: Type, ...) -> str`; the docstring becomes the
  tool description; `Literal[...]` parameter types are supported.
* **Dynamic instructions**: `@agent.instructions` on `def f(ctx: RunContext[Deps]) -> str`.
* **Exceptions**: `ModelHTTPError(status_code, model_name, body=...)` (construct in tests as
  `ModelHTTPError(429, "test", body=None)`), `.status_code`, `.body`; it subclasses `ModelAPIError`.
  Connection problems surface as `httpx2.TransportError` (e.g. `httpx2.ConnectError`) — catch both.
* **Testing without a network**
  * `from pydantic_ai.models.test import TestModel` → `Agent(TestModel(custom_output_args={...}), output_type=M)` returns that
    data as the validated output.
  * `from pydantic_ai.models.function import FunctionModel, AgentInfo`;
    `def fn(messages, info: AgentInfo) -> ModelResponse: return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args_dict)])`
    emulates an LLM that returns structured output; for a text-output agent return `ModelResponse(parts=[TextPart("...")])`;
    to call a tool return `ModelResponse(parts=[ToolCallPart("tool_name", {...})])`; tool results arrive in later calls as
    `ToolReturnPart` objects inside `messages[*].parts`.
  * `from pydantic_ai.messages import ModelResponse, ToolCallPart, TextPart, ToolReturnPart`.
* **Banner**: set `PYDANTIC_AI_NO_BANNER=1` to silence the startup banner in CLI output.
* **Known model-name facts (as of Oct 2026)**: `google:gemini-2.5-flash` returned HTTP 404 "no longer available to new
  users"; `google:gemini-3.8-flash` worked. Free-tier Gemini allows ~20 requests/day/model and sometimes returns 503
  "high demand". Use a current vision-capable model name for your key.

## 4. OS differences

| Task | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| Create venv | `python3 -m venv .venv` | `py -m venv .venv` |
| Activate | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| Python path | `.venv/bin/python` | `.venv\Scripts\python.exe` |
| Env var for one run | `CLAIM_TODAY=2026-10-12 uvicorn ...` | `$env:CLAIM_TODAY="2026-10-12"; uvicorn ...` |
| Find process on a port | `lsof -ti :8000` | `Get-NetTCPConnection -LocalPort 8000` |
| Fonts for the receipt generator | macOS Courier New/Menlo, Linux DejaVuSansMono, else Pillow's default | falls back to Pillow's default font (works, looks plainer) |

Run all project commands from the stated directory; `backend/pytest.ini` sets `pythonpath = .` so tests must be run
from `backend/`. Paths inside the code are computed from file locations (`ROOT = Path(__file__).resolve().parents[2]`
in `app/config.py`), so the server can be started from any directory as long as the module path is `app.main:app`
and the working directory is `backend/` (or `--app-dir backend`).
