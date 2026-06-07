"""Tests for agent_core.intent — LLM Intent Router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent_core.intent.fallback_rules import fallback_intent
from agent_core.intent.router import classify_intent_with_lite_model
from agent_core.intent.schemas import IntentResult
from agent_core.models.gateway import get_model_gateway, reset_model_gateway
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


@pytest.fixture(autouse=True)
def reset_gateway() -> None:
    """Reset gateway singleton before each test."""
    reset_gateway_fn()
    yield


def reset_gateway_fn() -> None:
    """Reset gateway singleton."""
    reset_model_gateway()


class TestFallbackIntent:
    """Verify fallback rule-based intent classification."""

    def test_hello_is_smalltalk(self) -> None:
        """'你好' should be classified as smalltalk."""
        result = fallback_intent("你好")
        assert result.intent == "smalltalk"

    def test_hello_english_is_smalltalk(self) -> None:
        """'hello' should be classified as smalltalk."""
        result = fallback_intent("hello")
        assert result.intent == "smalltalk"

    def test_slash_command(self) -> None:
        """/run should be classified as command."""
        result = fallback_intent("/run test query")
        assert result.intent == "command"

    def test_geant4_keyword_simulation(self) -> None:
        """Geant4 keyword should trigger simulation_request."""
        result = fallback_intent("建立一个 Geant4 仿真")
        assert result.intent == "simulation_request"
        assert result.requires_job is True
        assert result.requires_simulation_pipeline is True

    def test_unknown_input(self) -> None:
        """Ambiguous input should be unknown."""
        result = fallback_intent("今天天气怎么样")
        assert result.intent == "unknown"
        assert result.requires_clarification is True

    def test_active_job_context(self) -> None:
        """has_active_job should be passed through."""
        result = fallback_intent("继续", has_active_job=True)
        # "继续" doesn't match smalltalk or simulation keywords in fallback
        assert result.intent == "unknown"


class TestClassifyIntentWithLiteModel:
    """Verify LLM-based intent classification."""

    @pytest.mark.asyncio
    async def test_slash_command_short_circuit(self) -> None:
        """Slash commands should be short-circuited without LLM call."""
        result = await classify_intent_with_lite_model("/run test")
        assert result.intent == "command"
        assert result.extracted_command == "/run"

    @pytest.mark.asyncio
    async def test_llm_classifies_smalltalk(self) -> None:
        """LLM should classify '你好' as smalltalk."""
        mock_result = ModelCallResult(
            task=ModelTask.INTENT_ROUTING,
            tier=ModelTier.LITE,
            provider=ModelProvider.MOCK,
            model_name="mock-lite",
            content='{"intent": "smalltalk", "confidence": 0.99, '
                    '"routing_reason": "test", "normalized_user_query": "你好"}',
            parsed_json={
                "intent": "smalltalk",
                "confidence": 0.99,
                "routing_reason": "test",
                "normalized_user_query": "你好",
            },
        )

        with patch.object(
            get_model_gateway(), "call", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await classify_intent_with_lite_model("你好")

        assert result.intent == "smalltalk"
        assert result.confidence == 0.99

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back(self) -> None:
        """LLM failure should trigger fallback rules."""
        mock_result = ModelCallResult(
            task=ModelTask.INTENT_ROUTING,
            tier=ModelTier.LITE,
            provider=ModelProvider.MOCK,
            model_name="mock-lite",
            content="",
            error="API error",
        )

        with patch.object(
            get_model_gateway(), "call", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await classify_intent_with_lite_model("你好")

        # Should fall back to rule-based classification
        assert result.intent == "smalltalk"
        assert "lite model failed" in result.routing_reason

    @pytest.mark.asyncio
    async def test_invalid_json_falls_back(self) -> None:
        """Invalid JSON from LLM should trigger fallback."""
        mock_result = ModelCallResult(
            task=ModelTask.INTENT_ROUTING,
            tier=ModelTier.LITE,
            provider=ModelProvider.MOCK,
            model_name="mock-lite",
            content="not valid json at all",
            parsed_json=None,
        )

        with patch.object(
            get_model_gateway(), "call", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await classify_intent_with_lite_model("你好")

        # Should fall back
        assert result.intent == "smalltalk"

    @pytest.mark.asyncio
    async def test_uses_lite_tier(self) -> None:
        """Intent routing should use LITE tier."""
        calls = []

        async def mock_call(*args, **kwargs):
            calls.append(kwargs)
            return ModelCallResult(
                task=ModelTask.INTENT_ROUTING,
                tier=ModelTier.LITE,
                provider=ModelProvider.MOCK,
                model_name="mock-lite",
                content='{"intent": "smalltalk", "confidence": 0.9, '
                        '"routing_reason": "test", "normalized_user_query": "hi"}',
                parsed_json={
                    "intent": "smalltalk",
                    "confidence": 0.9,
                    "routing_reason": "test",
                    "normalized_user_query": "hi",
                },
            )

        with patch.object(
            get_model_gateway(), "call", side_effect=mock_call
        ):
            await classify_intent_with_lite_model("hi")

        assert calls[0]["tier"] == ModelTier.LITE
