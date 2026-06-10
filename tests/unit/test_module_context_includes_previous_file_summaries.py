"""Test that module context includes previous file summaries."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.g4_codegen.module_agents.module_context_builder import build_module_context


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestModuleContextIncludesPreviousFileSummaries:
    """Verify build_module_context includes existing_generated_file_summaries."""

    def test_includes_empty_summaries_by_default(self, workspace: Path) -> None:
        """When no previous files, existing_generated_file_summaries should be empty list."""
        ctx = build_module_context(
            module_name="beam_physics",
            module_contract={"module_name": "beam_physics", "module_type": "beam_physics"},
            g4_model_ir={"model_ir_id": "test", "physics": {"physics_list": "FTFP_BERT"}},
            codegen_plan={"required_modules": ["beam_physics"]},
            geometry_strategy_plan={},
            code_architecture_plan={},
            job_id="test_ctx",
            run_mode="strict",
        )

        assert "existing_generated_file_summaries" in ctx
        assert ctx["existing_generated_file_summaries"] == []

    def test_includes_provided_summaries(self, workspace: Path) -> None:
        """When summaries are provided, they should appear in context."""
        summaries = [
            {
                "module_name": "simulation_core",
                "path": "src/MaterialRegistry.cc",
                "generated_by": "simulation_core_module_agent",
                "classes": ["MaterialRegistry"],
                "public_methods": ["DefineMaterials"],
                "includes": ["G4NistManager.hh"],
                "provided_symbols": ["MaterialRegistry"],
            },
        ]

        ctx = build_module_context(
            module_name="runtime_app",
            module_contract={"module_name": "runtime_app", "module_type": "runtime_app"},
            g4_model_ir={"model_ir_id": "test"},
            codegen_plan={"required_modules": ["runtime_app"]},
            geometry_strategy_plan={},
            code_architecture_plan={},
            job_id="test_ctx2",
            run_mode="strict",
            existing_file_summaries=summaries,
        )

        assert ctx["existing_generated_file_summaries"] == summaries

    def test_context_has_required_fields(self, workspace: Path) -> None:
        """Context should have all required fields for a module agent."""
        ctx = build_module_context(
            module_name="beam_physics",
            module_contract={"module_name": "beam_physics"},
            g4_model_ir={"model_ir_id": "test"},
            codegen_plan={},
            geometry_strategy_plan={},
            code_architecture_plan={},
            job_id="test_ctx3",
            run_mode="strict",
        )

        required_keys = [
            "module_name",
            "module_contract",
            "g4_model_ir_subset",
            "codegen_plan",
            "geometry_strategy_plan",
            "code_architecture_plan",
            "geant4_api_rules",
            "existing_generated_file_summaries",
            "run_mode",
        ]
        for key in required_keys:
            assert key in ctx, f"Missing key in context: {key}"
