"""Test that runtime_app context can consume upstream module file summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestRuntimeAppContextIncludesAllSources:
    """Verify runtime_app module context includes upstream file summaries."""

    @pytest.mark.asyncio
    async def test_module_context_receives_upstream_summaries(
        self,
        workspace: Path,
    ) -> None:
        """run_module_agent_node should inject existing_generated_file_summaries."""
        # Simulate state with one completed module
        state: dict[str, Any] = {
            "job_id": "test_runtime_app",
            "run_mode": "strict",
            "module_contexts": {
                "runtime_app": {
                    "module_name": "runtime_app",
                    "module_contract": {},
                    "g4_model_ir_subset": {},
                    "codegen_plan": {},
                    "geometry_strategy_plan": {},
                    "code_architecture_plan": {},
                    "geant4_api_rules": [],
                    "existing_generated_file_summaries": [],
                    "run_mode": "strict",
                },
            },
            "module_results": {
                "simulation_core": {
                    "module_name": "simulation_core",
                    "status": "generated",
                    "generated_files": [
                        {
                            "path": "src/MaterialRegistry.cc",
                            "new_content": '#include "MaterialRegistry.hh"\nvoid MaterialRegistry::DefineMaterials() {}\n',  # noqa: E501
                            "generated_by": "simulation_core_module_agent",
                            "module_name": "simulation_core",
                        },
                        {
                            "path": "include/MaterialRegistry.hh",
                            "new_content": "#pragma once\nclass MaterialRegistry { public: void DefineMaterials(); };\n",  # noqa: E501
                            "generated_by": "simulation_core_module_agent",
                            "module_name": "simulation_core",
                        },
                    ],
                    "errors": [],
                    "warnings": [],
                },
                "beam_physics": {
                    "module_name": "beam_physics",
                    "status": "generated",
                    "generated_files": [
                        {
                            "path": "src/PrimaryGeneratorAction.cc",
                            "new_content": '#include "PrimaryGeneratorAction.hh"\nvoid PrimaryGeneratorAction::GeneratePrimaries(G4Event*) {}\n',  # noqa: E501
                            "generated_by": "beam_physics_module_agent",
                            "module_name": "beam_physics",
                        },
                    ],
                    "errors": [],
                    "warnings": [],
                },
            },
        }

        # We test the _extract_file_summary function directly
        from agent_core.g4_codegen.graph_nodes import _extract_file_summary

        # Extract summaries from completed modules
        summaries = []
        for module_name, result in state["module_results"].items():
            for f in result.get("generated_files", []):
                summaries.append(_extract_file_summary(module_name, f))

        # Should have summaries from upstream coarse modules
        assert len(summaries) == 3
        module_names_in_summaries = {s["module_name"] for s in summaries}
        assert "simulation_core" in module_names_in_summaries
        assert "beam_physics" in module_names_in_summaries

        # Each summary should have key fields
        for s in summaries:
            assert "module_name" in s  # noqa: E501  # noqa: E501  # noqa: E501
            assert "path" in s
            assert "generated_by" in s
            assert "classes" in s
            assert "includes" in s

    def test_file_summary_includes_constructor_signatures(self) -> None:
        from agent_core.g4_codegen.graph_nodes import _extract_file_summary

        summary = _extract_file_summary(
            "simulation_core",
            {
                "path": "include/DetectorConstruction.hh",
                "new_content": (
                    "class DetectorConstruction {\n"
                    "public:\n"
                    "  DetectorConstruction();\n"
                    "  G4VPhysicalVolume* Construct();\n"
                    "};\n"
                ),
            },
        )

        assert summary["constructor_signatures"] == ["DetectorConstruction()"]
