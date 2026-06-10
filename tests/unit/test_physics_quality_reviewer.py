from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from agent_core.g4_codegen.physics_quality_reviewer import run_physics_quality_reviewer
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier


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


def test_physics_quality_reviewer_prompt_audits_composite_source_parameters() -> None:
    from agent_core.g4_codegen.physics_quality_reviewer import PHYSICS_REVIEW_SYSTEM_PROMPT

    prompt = PHYSICS_REVIEW_SYSTEM_PROMPT.lower()
    assert "all g4modelir sources" in prompt
    assert "spectrum" in prompt
    assert "angular_distribution" in prompt
    assert "relative_weight" in prompt
