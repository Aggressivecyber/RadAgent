"""Test that cross-file LLM gate uses code_review_bundle, not just content_length."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier

from agent_core.g4_codegen.integration.cross_file_llm_gate import run_cross_file_llm_gate
from agent_core.models.gateway import reset_model_gateway


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_model_gateway()
    yield
    reset_model_gateway()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestCrossFileLlmGateUsesCodeReviewBundle:
    """Verify cross_file_llm_gate builds a code review bundle for the LLM."""

    @pytest.mark.asyncio
    async def test_builds_review_bundle(self, workspace: Path) -> None:
        """Cross-file LLM gate should build a file summary bundle for LLM."""
        proposed_patch = {
            "changed_files": [
                {
                    "path": "src/Detector.cc",
                    "new_content": '#include "Detector.hh"\nG4VPhysicalVolume* Detector::Construct() { return nullptr; }\n',
                    "generated_by": "geometry_module_agent",
                    "module_name": "geometry",
                },
                {
                    "path": "src/Physics.cc",
                    "new_content": '#include "Physics.hh"\nclass Physics {};\n',
                    "generated_by": "physics_module_agent",
                    "module_name": "physics",
                },
            ],
        }
        module_gate_results = {
            "geometry": {
                "hard": {"status": "pass"},
                "llm": {"status": "pass"},
            },
            "physics": {
                "hard": {"status": "pass"},
                "llm": {"status": "pass"},
            },
        }

        # Need to create the cross_file_hard_gate.json to pass the pre-check
        job_id = "test_bundle"
        from agent_core.config.workspace import get_job_dir
        codegen_dir = get_job_dir(job_id) / "06_codegen"
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / "cross_file_hard_gate.json").write_text(
            json.dumps({"status": "pass"})
        )

        captured_prompts: dict[str, str] = {}

        with patch(
            "agent_core.g4_codegen.integration.cross_file_llm_gate.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            async def capture_call(**kwargs):
                captured_prompts["user_prompt"] = kwargs.get("user_prompt", "")
                return ModelCallResult(
                    task=ModelTask.GATE_EXPLANATION,
                    tier=ModelTier.MAX,
                    provider=ModelProvider.MOCK,
                    model_name="mock",
                    content='{"status": "pass", "checks": [], "risks": [], "required_fixes": [], "requires_human_confirmation": false, "reviewer_notes": "OK"}',
                    parsed_json={
                        "status": "pass",
                        "checks": [],
                        "risks": [],
                        "required_fixes": [],
                        "requires_human_confirmation": False,
                        "reviewer_notes": "OK",
                    },
                    usage={},
                    latency_ms=0.0,
                )

            mock_gw.call = capture_call

            result = await run_cross_file_llm_gate(
                proposed_patch, module_gate_results, job_id
            )

        assert result["status"] == "pass"

        # The user_prompt should contain file info beyond just content_length
        prompt = captured_prompts["user_prompt"]
        assert "Detector.cc" in prompt
        assert "Physics.cc" in prompt


class TestCrossFileLlmGateDoesNotOnlyUseContentLength:
    """Verify cross-file LLM gate passes more than just content_length."""

    @pytest.mark.asyncio
    async def test_passes_file_metadata(self, workspace: Path) -> None:
        """LLM gate should pass file metadata, not only content_length."""
        proposed_patch = {
            "changed_files": [
                {
                    "path": "src/Main.cc",
                    "new_content": "int main() { return 0; }",
                    "generated_by": "main_cmake_module_agent",
                    "module_name": "main_cmake",
                },
            ],
        }
        module_gate_results = {
            "main_cmake": {"hard": {"status": "pass"}, "llm": {"status": "pass"}},
        }

        job_id = "test_not_length"
        from agent_core.config.workspace import get_job_dir
        codegen_dir = get_job_dir(job_id) / "06_codegen"
        codegen_dir.mkdir(parents=True, exist_ok=True)
        (codegen_dir / "cross_file_hard_gate.json").write_text(
            json.dumps({"status": "pass"})
        )

        captured_prompts: dict[str, str] = {}

        with patch(
            "agent_core.g4_codegen.integration.cross_file_llm_gate.get_model_gateway",
        ) as mock_gw_cls:
            mock_gw = AsyncMock()
            mock_gw_cls.return_value = mock_gw

            async def capture_call(**kwargs):
                captured_prompts["user_prompt"] = kwargs.get("user_prompt", "")
                return ModelCallResult(
                    task=ModelTask.GATE_EXPLANATION,
                    tier=ModelTier.MAX,
                    provider=ModelProvider.MOCK,
                    model_name="mock",
                    content='{"status": "pass", "checks": [], "risks": [], "required_fixes": [], "requires_human_confirmation": false, "reviewer_notes": ""}',
                    parsed_json={
                        "status": "pass",
                        "checks": [],
                        "risks": [],
                        "required_fixes": [],
                        "requires_human_confirmation": False,
                        "reviewer_notes": "",
                    },
                    usage={},
                    latency_ms=0.0,
                )

            mock_gw.call = capture_call

            await run_cross_file_llm_gate(
                proposed_patch, module_gate_results, job_id
            )

        prompt = captured_prompts["user_prompt"]

        # Verify the prompt contains structured file data
        # It should have path and generated_by, not just content_length
        assert "path" in prompt or "Main.cc" in prompt
        assert "generated_by" in prompt or "module_name" in prompt
