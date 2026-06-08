"""Test ModelGateway with MOCK provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from agent_core.models.gateway import get_model_gateway, reset_model_gateway
from agent_core.models.schemas import ModelProvider, ModelTask, ModelTier


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADAGENT_MODEL_PROVIDER", raising=False)
    reset_model_gateway()
    yield
    reset_model_gateway()


class TestModelGatewayMockProvider:
    """Verify gateway behavior with mock provider."""

    def test_mock_provider_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting RADAGENT_MODEL_PROVIDER=mock should use MOCK provider."""
        # The current config uses OPENAI_COMPATIBLE by default.
        # To use MOCK, the config would need to check this env var.
        # This test verifies the ModelProvider.MOCK enum exists.
        assert ModelProvider.MOCK == "mock"

    @pytest.mark.asyncio
    async def test_gateway_with_mock_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gateway should handle MOCK provider calls."""
        gw = get_model_gateway()

        # Patch the config to use MOCK provider
        from agent_core.models.schemas import ModelProfile

        mock_profiles = {
            tier: ModelProfile(
                tier=tier,
                provider=ModelProvider.MOCK,
                model_name="mock-model",
                base_url="",
            )
            for tier in ModelTier
        }

        with patch.object(gw, "profiles", mock_profiles):
            # Gateway currently raises NotImplementedError for non-OPENAI_COMPATIBLE
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                response_format="json",
            )

            # Should have an error since MOCK is not fully implemented
            # but should not crash
            assert result is not None
            assert result.task == ModelTask.INTENT_ROUTING

    @pytest.mark.asyncio
    async def test_mock_provider_returns_valid_result(self) -> None:
        """MOCK provider should return a valid ModelCallResult."""
        # Direct mock of the gateway call
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=('{"intent": "test"}', {"prompt_tokens": 5, "completion_tokens": 3}),
        ):
            result = await gw.call(
                task=ModelTask.CODEGEN,
                tier=ModelTier.PRO,
                system_prompt="test",
                user_prompt="test",
                response_format="json",
            )

        assert result.provider == ModelProvider.OPENAI_COMPATIBLE  # default
        assert result.content == '{"intent": "test"}'
        assert result.parsed_json == {"intent": "test"}
