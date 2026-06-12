from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from agent_core.g4_codegen.physics_quality_reviewer import run_physics_quality_reviewer
from agent_core.models.schemas import (
    ModelCallResult,
    ModelProvider,
    ModelTask,
    ModelTier,
)


@pytest.mark.asyncio
async def test_physics_quality_reviewer_uses_lite_flash_tier(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    calls: list[dict[str, Any]] = []

    class Gateway:
        profiles = {ModelTier.LITE: SimpleNamespace(provider=ModelProvider.OPENAI_COMPATIBLE)}

        async def call(self, **kwargs: Any) -> ModelCallResult:
            calls.append(kwargs)
            payload = {
                "status": "pass",
                "overall_score": 95,
                "physics_model_score": 95,
                "source_fidelity_score": 95,
                "geometry_fidelity_score": 95,
                "transport_precision_score": 90,
                "output_validity_score": 95,
                "findings": [],
                "required_fixes": [],
                "reviewer_notes": "parameter consistency reviewed",
            }
            return ModelCallResult(
                task=kwargs["task"],
                tier=kwargs["tier"],
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="flash-test",
                content=json.dumps(payload),
                parsed_json=payload,
            )

    monkeypatch.setattr(
        "agent_core.g4_codegen.physics_quality_reviewer.get_model_gateway",
        lambda: Gateway(),
    )

    review = await run_physics_quality_reviewer(
        proposed_patch={"changed_files": []},
        g4_model_ir={"sources": [], "physics": {}},
        module_contracts={},
        module_contexts={},
        global_integration_report={"status": "passed"},
        job_id="physics_review_lite",
    )

    assert review["status"] == "pass"
    assert calls
    assert calls[0]["task"] == ModelTask.CONTEXT_SUMMARY
    assert calls[0]["tier"] == ModelTier.LITE
    assert calls[0]["metadata"]["module_name"] == "physics_quality_reviewer"
    assert calls[0]["metadata"]["enable_thinking"] is False
    assert review["summary_model"]["tier"] == str(ModelTier.LITE)
    assert review["summary_model"]["model_name"] == "flash-test"


@pytest.mark.asyncio
async def test_physics_quality_reviewer_prompt_prioritizes_latest_runtime_pass(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    calls: list[dict[str, Any]] = []

    class Gateway:
        profiles = {ModelTier.LITE: SimpleNamespace(provider=ModelProvider.OPENAI_COMPATIBLE)}

        async def call(self, **kwargs: Any) -> ModelCallResult:
            calls.append(kwargs)
            payload = {
                "status": "pass",
                "overall_score": 95,
                "physics_model_score": 95,
                "source_fidelity_score": 95,
                "geometry_fidelity_score": 95,
                "transport_precision_score": 90,
                "output_validity_score": 95,
                "findings": [],
                "required_fixes": [],
                "reviewer_notes": "latest runtime facts reviewed",
            }
            return ModelCallResult(
                task=kwargs["task"],
                tier=kwargs["tier"],
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="flash-test",
                content=json.dumps(payload),
                parsed_json=payload,
            )

    monkeypatch.setattr(
        "agent_core.g4_codegen.physics_quality_reviewer.get_model_gateway",
        lambda: Gateway(),
    )

    await run_physics_quality_reviewer(
        proposed_patch={"changed_files": []},
        g4_model_ir={"sources": [{"events": 5}], "physics": {}},
        module_contracts={},
        module_contexts={},
        global_integration_report={
            "status": "passed",
            "runtime_gate_attempts": [
                {
                    "attempt": 1,
                    "status": "fail",
                    "errors": ["old compile failed"],
                    "missing_outputs": ["g4_summary.json"],
                },
                {
                    "attempt": 2,
                    "status": "pass",
                    "expected_events": 5,
                    "missing_outputs": [],
                    "errors": [],
                    "output_quality": {
                        "status": "pass",
                        "errors": [],
                        "metrics": {
                            "events_requested": 5,
                            "expected_events": 5,
                            "event_table_rows": 5,
                            "event_table_nonzero_rows": 5,
                        },
                    },
                },
            ],
        },
        job_id="physics_review_runtime_priority",
    )

    context = json.loads(calls[0]["user_prompt"])
    summary = context["runtime_verification_summary"]
    assert summary["latest_attempt"] == 2
    assert summary["latest_runtime_gate_status"] == "pass"
    assert summary["latest_runtime_gate_passed"] is True
    assert summary["missing_outputs"] == []
    assert summary["output_quality_status"] == "pass"
    assert summary["event_table_rows"] == 5
    assert summary["prior_failed_attempt_count"] == 1
    assert "latest passing runtime gate" in context["review_instruction"]


def test_physics_quality_reviewer_prompt_audits_composite_source_parameters() -> None:
    from agent_core.g4_codegen.physics_quality_reviewer import PHYSICS_REVIEW_SYSTEM_PROMPT

    prompt = PHYSICS_REVIEW_SYSTEM_PROMPT.lower()
    assert "all g4modelir sources" in prompt
    assert "spectrum" in prompt
    assert "angular_distribution" in prompt
    assert "relative_weight" in prompt
