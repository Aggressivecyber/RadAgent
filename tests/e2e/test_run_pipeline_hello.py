"""E2E test: run_pipeline with '你好' should not enter simulation pipeline."""

from __future__ import annotations

import json
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


@pytest.mark.asyncio
async def test_run_pipeline_hello_terminates() -> None:
    """run_pipeline with '你好' should terminate with smalltalk intent."""
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
        result = await graph.ainvoke({
            "user_query": "你好",
            "run_mode": "dev",
        })

    # Should be classified as smalltalk
    assert result["intent"] == "smalltalk"
    assert result["response_status"] == "answered"
    assert result["pipeline_terminated"] is True

    # Should NOT have any simulation artifacts
    assert not result.get("task_spec_path")
    assert not result.get("g4_model_ir_path")
    assert not result.get("proposed_patch_path")
    assert not result.get("gate_results_path")
    assert not result.get("artifact_manifest_path")
    assert not result.get("job_id")


@pytest.mark.asyncio
async def test_run_pipeline_simulation_enters_pipeline() -> None:
    """run_pipeline with simulation request should enter pipeline."""
    graph = compile_main_graph()

    # Mock all the LLM calls needed for a simulation request
    mock_responses = {
        "intent": (
            '{"intent": "simulation_request", "confidence": 0.95, '
            '"routing_reason": "test", "normalized_user_query": "建立探测器", '
            '"requires_job": true, "requires_simulation_pipeline": true}',
            {},
        ),
    }

    call_count = 0

    async def mock_llm_call(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call is intent routing
        if call_count == 1:
            return mock_responses["intent"]
        # Subsequent calls return generic responses
        return ("{}", {})

    with patch(
        "agent_core.models.gateway.call_openai_compatible_model",
        side_effect=mock_llm_call,
    ):
        result = await graph.ainvoke({
            "user_query": "建立一个9组件硅探测器，10MeV proton入射",
            "run_mode": "dev",
        })

    # Should be classified as simulation_request
    assert result["intent"] == "simulation_request"
    # Should have entered the pipeline (job_id should be set)
    assert result.get("job_id")
