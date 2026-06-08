"""Test that mock GATE_EXPLANATION returns correct structured JSON."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from agent_core.g4_codegen.module_gates.llm_gate_base import run_llm_gate
from agent_core.models.gateway import get_model_gateway, reset_model_gateway
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

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(
                '{"status": "pass", "checks": [], "risks": [], "required_fixes": [], "requires_human_confirmation": false, "reviewer_notes": "OK"}',  # noqa: E501
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
                '{"status": "fail", "checks": [], "risks": ["risk1"], "required_fixes": ["fix missing include"], "requires_human_confirmation": false, "reviewer_notes": "Found issues."}',  # noqa: E501
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

    @pytest.mark.asyncio
    async def test_run_llm_gate_normalizes_string_semantic_checks(self) -> None:
        """Provider string checks should be normalized to structured check dicts."""
        with patch(
            "agent_core.g4_codegen.module_gates.llm_gate_base.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw
            mock_result = AsyncMock()
            mock_result.error = None
            mock_result.content = "{}"
            mock_result.parsed_json = {
                "status": "pass",
                "overall_score": 0.95,
                "dimensions": {
                    "contract_compliance": 0.95,
                    "geant4_correctness": 0.95,
                    "interface_consistency": 0.95,
                    "hallucination_risk": 0.95,
                    "compile_risk": 0.95,
                },
                "semantic_checks": ["IR materials are covered"],
                "risks": [],
                "blocking_issues": [],
                "required_fixes": [],
                "reviewer_notes": "OK",
            }
            mock_gw.call.return_value = mock_result

            result = await run_llm_gate(
                "material",
                {"module_name": "material"},
                [
                    {
                        "path": "include/MaterialRegistry.hh",
                        "new_content": "class MaterialRegistry {};",
                    }
                ],
                {"status": "pass"},
            )

        assert result.status == "pass"
        assert result.scorecard["overall_score"] == 0.95
        assert result.checks == [
            {
                "check": "semantic_check_1",
                "status": "pass",
                "message": "IR materials are covered",
            }
        ]
