"""Tests for agent_core.models.gateway — model gateway."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from agent_core.models.gateway import get_model_gateway, reset_model_gateway
from agent_core.models.schemas import (
    ModelCallResult,
    ModelTask,
    ModelTier,
)


@pytest.fixture(autouse=True)
def reset_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset gateway singleton and ensure non-mock provider for standard tests."""
    monkeypatch.delenv("RADAGENT_MODEL_PROVIDER", raising=False)
    reset_model_gateway()
    yield
    reset_model_gateway()


class TestModelGateway:
    """Verify ModelGateway behavior."""

    def test_singleton_creation(self) -> None:
        """get_model_gateway should return same instance."""
        gw1 = get_model_gateway()
        gw2 = get_model_gateway()
        assert gw1 is gw2

    def test_singleton_reset(self) -> None:
        """reset_model_gateway should create new instance."""
        gw1 = get_model_gateway()
        reset_model_gateway()
        gw2 = get_model_gateway()
        assert gw1 is not gw2

    @pytest.mark.asyncio
    async def test_call_returns_result(self) -> None:
        """Gateway call should return ModelCallResult."""
        gw = get_model_gateway()

        mock_content = '{"intent": "smalltalk"}'
        mock_usage = {"prompt_tokens": 10, "completion_tokens": 5}

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(mock_content, mock_usage),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                response_format="json",
            )

        assert isinstance(result, ModelCallResult)
        assert result.task == ModelTask.INTENT_ROUTING
        assert result.tier == ModelTier.LITE  # INTENT_ROUTING defaults to LITE
        assert result.content == mock_content
        assert result.parsed_json == {"intent": "smalltalk"}
        assert result.usage == mock_usage
        assert result.error is None

    @pytest.mark.asyncio
    async def test_call_with_explicit_tier(self) -> None:
        """Gateway should use explicit tier when provided."""
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=("ok", {}),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                tier=ModelTier.MAX,
            )

        assert result.tier == ModelTier.MAX

    @pytest.mark.asyncio
    async def test_call_handles_error(self) -> None:
        """Gateway should handle errors gracefully."""
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API error"),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
            )

        assert result.error == "API error"
        assert result.content == ""
        assert result.parsed_json is None

    @pytest.mark.asyncio
    async def test_call_json_parse(self) -> None:
        """Gateway should parse JSON responses."""
        gw = get_model_gateway()

        json_content = '{"key": "value"}'
        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(json_content, {}),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                response_format="json",
            )

        assert result.parsed_json == {"key": "value"}

    @pytest.mark.asyncio
    async def test_call_json_parse_with_markdown(self) -> None:
        """Gateway should extract JSON from markdown code fences."""
        gw = get_model_gateway()

        json_content = '```json\n{"key": "value"}\n```'
        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(json_content, {}),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                response_format="json",
            )

        assert result.parsed_json == {"key": "value"}
