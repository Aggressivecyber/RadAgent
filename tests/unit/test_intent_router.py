"""Tests for agent_core.intent — two-class LM intent router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from agent_core.intent.fallback_rules import fallback_intent
from agent_core.intent.router import classify_intent_with_lite_model
from agent_core.models.gateway import get_model_gateway, reset_model_gateway
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


@pytest.fixture(autouse=True)
def reset_gateway() -> None:
    reset_model_gateway()
    yield


def _mock_result(parsed_json: dict) -> ModelCallResult:
    return ModelCallResult(
        task=ModelTask.INTENT_ROUTING,
        tier=ModelTier.LITE,
        provider=ModelProvider.MOCK,
        model_name="mock-lite",
        content="{}",
        parsed_json=parsed_json,
    )


class TestFallbackIntent:
    """Fallback must not infer intent from keywords."""

    def test_fallback_defaults_to_chat_for_any_text(self) -> None:
        result = fallback_intent("建立一个 Geant4 仿真")
        assert result.intent == "chat"
        assert result.intent_detail == "unknown"
        assert result.requires_job is False
        assert result.requires_simulation_pipeline is False

    def test_fallback_defaults_to_chat_without_rule_based_guessing(self) -> None:
        result = fallback_intent("继续")
        assert result.intent == "chat"
        assert result.requires_simulation_pipeline is False


class TestClassifyIntentWithLiteModel:
    """Verify LM-based intent classification and contract normalization."""

    @pytest.mark.asyncio
    async def test_llm_classifies_chat(self) -> None:
        mock_result = _mock_result(
            {
                "intent": "chat",
                "intent_detail": "smalltalk",
                "confidence": 0.99,
                "routing_reason": "test",
                "normalized_user_query": "你好",
            }
        )

        with patch.object(
            get_model_gateway(), "call", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await classify_intent_with_lite_model("你好")

        assert result.intent == "chat"
        assert result.intent_detail == "smalltalk"
        assert result.confidence == 0.99

    @pytest.mark.asyncio
    async def test_llm_classifies_simulation_work(self) -> None:
        mock_result = _mock_result(
            {
                "intent": "simulation_work",
                "intent_detail": "simulation_request",
                "confidence": 0.94,
                "routing_reason": "test",
                "normalized_user_query": "建立 Geant4 仿真",
            }
        )

        with patch.object(
            get_model_gateway(), "call", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await classify_intent_with_lite_model("建立 Geant4 仿真")

        assert result.intent == "simulation_work"
        assert result.intent_detail == "simulation_request"
        assert result.requires_job is True
        assert result.requires_simulation_pipeline is True

    @pytest.mark.asyncio
    async def test_detail_only_chat_label_is_normalized(self) -> None:
        mock_result = _mock_result(
            {
                "intent": "help",
                "confidence": 0.9,
                "routing_reason": "detail-only label",
                "normalized_user_query": "怎么用",
            }
        )

        with patch.object(
            get_model_gateway(), "call", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await classify_intent_with_lite_model("怎么用")

        assert result.intent == "chat"
        assert result.intent_detail == "help"
        assert result.requires_simulation_pipeline is False

    @pytest.mark.asyncio
    async def test_detail_only_simulation_label_is_normalized(self) -> None:
        mock_result = _mock_result(
            {
                "intent": "simulation_request",
                "confidence": 0.9,
                "routing_reason": "detail-only label",
                "normalized_user_query": "run a detector simulation",
            }
        )

        with patch.object(
            get_model_gateway(), "call", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await classify_intent_with_lite_model("run a detector simulation")

        assert result.intent == "simulation_work"
        assert result.intent_detail == "simulation_request"
        assert result.requires_simulation_pipeline is True

    @pytest.mark.asyncio
    async def test_slash_text_is_sent_to_lm_not_short_circuited(self) -> None:
        mock_call = AsyncMock(
            return_value=_mock_result(
                {
                    "intent": "chat",
                    "intent_detail": "general_question",
                    "confidence": 0.8,
                    "routing_reason": "lm decided",
                    "normalized_user_query": "/run test",
                }
            )
        )

        with patch.object(get_model_gateway(), "call", mock_call):
            result = await classify_intent_with_lite_model("/run test")

        assert result.intent == "chat"
        mock_call.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_llm_failure_defaults_to_chat(self) -> None:
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
            result = await classify_intent_with_lite_model("建立 Geant4 仿真")

        assert result.intent == "chat"
        assert result.requires_simulation_pipeline is False
        assert "lite model failed" in result.routing_reason

    @pytest.mark.asyncio
    async def test_uses_lite_tier(self) -> None:
        calls = []

        async def mock_call(*args, **kwargs):
            calls.append(kwargs)
            return _mock_result(
                {
                    "intent": "chat",
                    "confidence": 0.9,
                    "routing_reason": "test",
                    "normalized_user_query": "hi",
                }
            )

        with patch.object(get_model_gateway(), "call", side_effect=mock_call):
            await classify_intent_with_lite_model("hi")

        assert calls[0]["tier"] == ModelTier.LITE
