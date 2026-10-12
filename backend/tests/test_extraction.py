import asyncio
import io
from dataclasses import replace
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.config import Settings
from app.extraction import build_agent, extract_receipt

GOOD = {
    "readable": True,
    "vendor": "Bluebird Cafe",
    "receipt_date": "2026-09-14",
    "total": 412.0,
    "tax": 19.62,
    "currency": "inr",
    "category": "meals",
    "line_items": [],
    "confidence": {"vendor": 0.9, "date": 0.9, "total": 0.9},
}


@pytest.fixture
def receipt_file(tmp_path):
    p = tmp_path / "secret_scenario_name.png"
    buf = io.BytesIO()
    Image.new("RGB", (200, 300), "white").save(buf, "PNG")
    p.write_bytes(buf.getvalue())
    return p


@pytest.fixture
def settings(tmp_path):
    return Settings(
        llm_model="test:model",
        llm_call_delay_s=0,
        use_extraction_cache=False,
        cache_dir=tmp_path / "cache",
    )


def run(coro):
    return asyncio.run(coro)


def test_successful_extraction_normalises_and_caches(receipt_file, settings):
    agent = build_agent(TestModel(custom_output_args=GOOD))
    result = run(extract_receipt(receipt_file, agent=agent, settings=settings))

    assert result.error is None
    assert result.receipt.currency == "INR"
    assert result.total_inr == 412.0
    assert result.needs_review is False
    assert len(list(settings.cache_dir.rglob("*.json"))) == 1


def test_foreign_currency_converted(receipt_file, settings):
    agent = build_agent(TestModel(custom_output_args={**GOOD, "currency": "USD", "total": 10.0}))
    result = run(extract_receipt(receipt_file, agent=agent, settings=settings))
    assert result.total_inr == 830.0


def test_cache_hit_skips_the_llm(receipt_file, settings):
    agent = build_agent(TestModel(custom_output_args=GOOD))
    first = run(extract_receipt(receipt_file, agent=agent, settings=settings))

    class Boom:
        async def run(self, *a, **k):
            raise AssertionError("LLM must not be called on cache hit")

    cached_settings = replace(settings, use_extraction_cache=True)
    again = run(extract_receipt(receipt_file, agent=Boom(), settings=cached_settings))
    assert again.receipt == first.receipt


def test_persistent_invalid_output_returns_error_result(receipt_file, settings):
    def bad(messages, info: AgentInfo):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"currency": "??"})])

    agent = build_agent(FunctionModel(bad))
    result = run(extract_receipt(receipt_file, agent=agent, settings=settings))

    assert result.receipt is None
    assert result.needs_review is True
    assert result.error
    assert not list(settings.cache_dir.rglob("*.json"))  # failures are not cached


def test_file_name_is_not_sent_to_the_model(receipt_file, settings):
    seen: list[str] = []

    def spy(messages, info: AgentInfo):
        seen.append(str(messages))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, GOOD)])

    run(extract_receipt(receipt_file, agent=build_agent(FunctionModel(spy)), settings=settings))
    assert seen and "secret_scenario_name" not in seen[0]


def test_rate_limit_is_retried(receipt_file, settings, monkeypatch):
    calls = {"n": 0}

    class Flaky:
        async def run(self, content):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ModelHTTPError(429, "test", body=None)
            from app.models import Receipt

            return SimpleNamespace(output=Receipt.model_validate(GOOD))

    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.extraction.asyncio.sleep", no_sleep)
    result = run(extract_receipt(receipt_file, agent=Flaky(), settings=settings))
    assert calls["n"] == 2
    assert result.error is None


def test_daily_quota_is_not_retried(receipt_file, settings):
    calls = {"n": 0}

    class OutOfQuota:
        async def run(self, content):
            calls["n"] += 1
            raise ModelHTTPError(
                429, "test", body={"error": {"message": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}}
            )

    with pytest.raises(ModelHTTPError):
        run(extract_receipt(receipt_file, agent=OutOfQuota(), settings=settings))
    assert calls["n"] == 1


def test_non_retryable_http_error_propagates(receipt_file, settings):
    class Unauthorized:
        async def run(self, content):
            raise ModelHTTPError(401, "test", body=None)

    with pytest.raises(ModelHTTPError):
        run(extract_receipt(receipt_file, agent=Unauthorized(), settings=settings))
