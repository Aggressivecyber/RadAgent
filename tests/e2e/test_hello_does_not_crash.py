"""E2E test: '你好' should not crash and should return smalltalk intent.

This is a critical P0 test — the system must handle casual greetings
without entering the simulation pipeline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent_core.graph.main_graph import compile_main_graph
from agent_core.models.gateway import reset_model_gateway
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


@pytest.fixture(autouse=True)
def reset_gateway() -> None:
    """Reset gateway singleton before each test."""
    reset_model_gateway()
    yield
    reset_model_gateway()


def _make_smalltalk_result() -> ModelCallResult:
    """Create a mock result for smalltalk intent."""
    return ModelCallResult(
        task=ModelTask.INTENT_ROUTING,
        tier=ModelTier.LITE,
        provider=ModelProvider.MOCK,
        model_name="mock-lite",
        content='{"intent": "smalltalk", "confidence": 0.99, '
                '"routing_reason": "User said hello", '
                '"normalized_user_query": "你好"}',
        parsed_json={
            "intent": "smalltalk",
            "confidence": 0.99,
            "routing_reason": "User said hello",
            "normalized_user_query": "你好",
        },
    )


@pytest.mark.asyncio
async def test_hello_does_not_crash() -> None:
    """'你好' should return smalltalk intent without crashing."""
    graph = compile_main_graph()

    with patch(
        "agent_core.models.gateway.call_openai_compatible_model",
        new_callable=AsyncMock,
        return_value=(
            '{"intent": "smalltalk", "confidence": 0.99, '
            '"routing_reason": "test", "normalized_user_query": "你好"}',
            {},
        ),
    ):
        result = await graph.ainvoke({"user_query": "你好", "run_mode": "dev"})

    assert result["intent"] == "smalltalk"
    assert result["response_status"] == "answered"
    assert result["pipeline_terminated"] is True
    # Must NOT enter simulation pipeline
    assert not result.get("task_spec_path")
    assert not result.get("g4_model_ir_path")
    assert not result.get("proposed_patch_path")
    assert not result.get("job_workspace")


@pytest.mark.asyncio
async def test_hello_english_does_not_crash() -> None:
    """'hello' should return smalltalk intent without crashing."""
    graph = compile_main_graph()

    with patch(
        "agent_core.models.gateway.call_openai_compatible_model",
        new_callable=AsyncMock,
        return_value=(
            '{"intent": "smalltalk", "confidence": 0.95, '
            '"routing_reason": "test", "normalized_user_query": "hello"}',
            {},
        ),
    ):
        result = await graph.ainvoke({"user_query": "hello", "run_mode": "dev"})

    assert result["intent"] == "smalltalk"
    assert result["response_status"] == "answered"
    assert result["pipeline_terminated"] is True
    assert not result.get("job_workspace")


@pytest.mark.asyncio
async def test_help_does_not_crash() -> None:
    """'你能做什么' should return help intent without crashing."""
    graph = compile_main_graph()

    with patch(
        "agent_core.models.gateway.call_openai_compatible_model",
        new_callable=AsyncMock,
        return_value=(
            '{"intent": "help", "confidence": 0.9, '
            '"routing_reason": "test", "normalized_user_query": "你能做什么"}',
            {},
        ),
    ):
        result = await graph.ainvoke({"user_query": "你能做什么", "run_mode": "dev"})

    assert result["intent"] == "help"
    assert result["response_status"] == "answered"
    assert result["pipeline_terminated"] is True
    assert not result.get("job_workspace")
