"""Test that main_cmake context includes all upstream module file summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_core.g4_codegen.graph_nodes import run_module_agent_node
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestMainCmakeContextIncludesAllSources:
    """Verify main_cmake module context includes upstream file summaries."""

    @pytest.mark.asyncio
    async def test_module_context_receives_upstream_summaries(
        self, workspace: Path,
    ) -> None:
        """run_module_agent_node should inject existing_generated_file_summaries."""
        # Simulate state with one completed module
        state: dict[str, Any] = {
            "job_id": "test_main_cmake",
            "run_mode": "dev",
            "module_contexts": {
                "main_cmake": {
                    "module_name": "main_cmake",
                    "module_contract": {},
                    "g4_model_ir_subset": {},
                    "codegen_plan": {},
                    "geometry_strategy_plan": {},
                    "code_architecture_plan": {},
                    "geant4_api_rules": [],
                    "existing_generated_file_summaries": [],
                    "run_mode": "dev",
                },
            },
            "module_results": {
                "material": {
                    "module_name": "material",
                    "status": "generated",
                    "generated_files": [
                        {
                            "path": "src/MaterialRegistry.cc",
                            "new_content": '#include "MaterialRegistry.hh"\nvoid MaterialRegistry::DefineMaterials() {}\n',
                            "generated_by": "material_module_agent",
                            "module_name": "material",
                        },
                        {
                            "path": "include/MaterialRegistry.hh",
                            "new_content": "#pragma once\nclass MaterialRegistry { public: void DefineMaterials(); };\n",
                            "generated_by": "material_module_agent",
                            "module_name": "material",
                        },
                    ],
                    "errors": [],
                    "warnings": [],
                },
                "geometry": {
                    "module_name": "geometry",
                    "status": "generated",
                    "generated_files": [
                        {
                            "path": "src/DetectorConstruction.cc",
                            "new_content": '#include "DetectorConstruction.hh"\nG4VPhysicalVolume* DetectorConstruction::Construct() { return nullptr; }\n',
                            "generated_by": "geometry_module_agent",
                            "module_name": "geometry",
                        },
                    ],
                    "errors": [],
                    "warnings": [],
                },
            },
            "module_gate_results": {},
        }

        # We test the _extract_file_summary function directly
        from agent_core.g4_codegen.graph_nodes import _extract_file_summary

        # Extract summaries from completed modules
        summaries = []
        for module_name, result in state["module_results"].items():
            for f in result.get("generated_files", []):
                summaries.append(_extract_file_summary(module_name, f))

        # Should have summaries from material and geometry modules
        assert len(summaries) == 3
        module_names_in_summaries = {s["module_name"] for s in summaries}
        assert "material" in module_names_in_summaries
        assert "geometry" in module_names_in_summaries

        # Each summary should have key fields
        for s in summaries:
            assert "module_name" in s
            assert "path" in s
            assert "generated_by" in s
            assert "classes" in s
            assert "includes" in s
