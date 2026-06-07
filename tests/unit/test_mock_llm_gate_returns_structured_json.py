"""Test that mock GATE_EXPLANATION returns correct structured JSON."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent_core.models.gateway import ModelGateway, get_model_gateway, reset_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADAGENT_MODEL_PROVIDER", raising=False)
    reset_model_gateway()
    yield
    reset_model_gateway()


class TestMockLlmGateReturnsStructuredJson:
    """Verify mock GATE_EXPLANATION returns correct JSON format."""

    @pytest.mark.asyncio
    async def test_gate_explanation_json_format(self) -> None:
        """Mock GATE_EXPLANATION should return correct JSON with required fields."""
        gw = get_model_gateway()

        gate_json = {
            "status": "pass",
            "checks": [
                {"check": "no_simplification", "status": "pass", "message": "OK"},
                {"check": "no_missing_includes", "status": "pass", "message": "OK"},
            ],
            "risks": [],
            "required_fixes": [],
            "requires_human_confirmation": False,
            "reviewer_notes": "All checks passed.",
        }

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(
                '{"status": "pass", "checks": [], "risks": [], "required_fixes": [], "requires_human_confirmation": false, "reviewer_notes": "OK"}',
                {"prompt_tokens": 100, "completion_tokens": 50},
            ),
        ):
            result = await gw.call(
                task=ModelTask.GATE_EXPLANATION,
                tier=ModelTier.MAX,
                system_prompt="You are a gate reviewer.",
                user_prompt="Review this code.",
                response_format="json",
            )

        assert result.error is None
        assert result.parsed_json is not None
        assert "status" in result.parsed_json

        # The expected fields for gate explanation
        data = result.parsed_json
        assert "status" in data
        assert data["status"] in ("pass", "fail")

    @pytest.mark.asyncio
    async def test_gate_explanation_fail_format(self) -> None:
        """Mock GATE_EXPLANATION with fail should include required_fixes."""
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(
                '{"status": "fail", "checks": [], "risks": ["risk1"], "required_fixes": ["fix missing include"], "requires_human_confirmation": false, "reviewer_notes": "Found issues."}',
                {"prompt_tokens": 100, "completion_tokens": 50},
            ),
        ):
            result = await gw.call(
                task=ModelTask.GATE_EXPLANATION,
                tier=ModelTier.MAX,
                system_prompt="review",
                user_prompt="review code",
                response_format="json",
            )

        data = result.parsed_json
        assert data["status"] == "fail"
        assert len(data["required_fixes"]) > 0
