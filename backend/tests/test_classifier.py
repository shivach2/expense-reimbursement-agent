import asyncio

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.classifier import UNKNOWN, build_classifier_agent, classify_receipt, describe_categories
from app.config import Settings
from app.models import ExtractedReceipt, FieldConfidence, LineItem, Receipt
from test_policy_evaluator import EMP, POLICY


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        llm_model="test:m",
        llm_call_delay_s=0,
        use_extraction_cache=False,
        cache_dir=tmp_path / "x",
        classification_cache_dir=tmp_path / "cls",
    )


def receipt(readable=True) -> ExtractedReceipt:
    r = Receipt(
        readable=readable,
        vendor="Lotus Grove Hotel",
        total=6000,
        currency="INR",
        category="hotel stay",
        nights=1,
        line_items=[LineItem(description="Room 1 night", amount=6000)],
        confidence=FieldConfidence(vendor=0.9, date=0.9, total=0.9),
    )
    return ExtractedReceipt(source_file="a.png", file_sha256="sha-a", model="m", receipt=r)


def answering(*answers: dict, seen: list | None = None):
    def fn(messages, info: AgentInfo):
        if seen is not None:
            seen.append(str(messages))
        n = len(seen) if seen is not None else 1
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, answers[min(n, len(answers)) - 1])])

    return FunctionModel(fn)


GOOD = {"category": "lodging", "reasoning": "A hotel room for one night.", "confidence": 0.97}


def test_classifies_into_a_policy_category_and_caches(settings):
    seen: list = []
    agent = build_classifier_agent(answering(GOOD, seen=seen))
    c = run(classify_receipt(receipt(), EMP, POLICY, agent=agent, settings=settings))
    assert c.category == "lodging" and not c.needs_clarification
    run(classify_receipt(receipt(), EMP, POLICY, agent=agent, settings=settings))
    assert len(seen) == 1  # second call came from the cache


def test_prompt_lists_policy_categories_and_grade_eligibility(settings):
    seen: list = []
    exec_emp = EMP.model_copy(update={"grade": "E1"})
    run(
        classify_receipt(
            receipt(), exec_emp, POLICY, agent=build_classifier_agent(answering(GOOD, seen=seen)), settings=settings
        )
    )
    text = seen[0]
    assert "lodging" in text and "NOT available to grade E1" in text and "never reimbursable" in text
    assert "Room 1 night" in text


def test_unknown_category_is_sent_back_to_the_model(settings):
    seen: list = []
    agent = build_classifier_agent(answering({**GOOD, "category": "hotels"}, GOOD, seen=seen))
    c = run(classify_receipt(receipt(), EMP, POLICY, agent=agent, settings=settings))
    assert c.category == "lodging" and len(seen) == 2


def test_persistently_invalid_output_falls_back_to_unknown(settings):
    agent = build_classifier_agent(answering({**GOOD, "category": "hotels"}))
    c = run(classify_receipt(receipt(), EMP, POLICY, agent=agent, settings=settings))
    assert c.category == UNKNOWN and c.needs_clarification


def test_unreadable_receipt_skips_the_llm(settings):
    class Boom:
        async def run(self, *a, **k):
            raise AssertionError("must not call the LLM")

    c = run(classify_receipt(receipt(readable=False), EMP, POLICY, agent=Boom(), settings=settings))
    assert c.category == UNKNOWN


def test_category_description_marks_exclusions():
    text = describe_categories(POLICY, EMP)
    assert "personal_expenses" in text and "[never reimbursable]" in text
    assert "lodging" in text and "[available to grade M2]" in text
