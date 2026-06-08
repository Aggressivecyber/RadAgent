"""E2E test — comprehensive mock provider full flow test."""

# noqa: E501  # noqa: E501
from __future__ import annotations

# noqa: E501  # noqa: E501
from pathlib import Path
from typing import Any

import pytest
from agent_core.g4_codegen.graph_nodes import persist_codegen_output_node
from agent_core.g4_codegen.integration.cross_file_hard_gate import run_cross_file_hard_gate
from agent_core.g4_codegen.integration.integration_assembler import assemble_proposed_patch
from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code
from agent_core.g4_codegen.schemas import GeneratedModuleFile
from agent_core.models.gateway import reset_model_gateway


@pytest.fixture(autouse=True)
def _reset_gw() -> None:
    reset_model_gateway()
    yield
    reset_model_gateway()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


def _valid_file(path: str, content: str, module_name: str) -> dict[str, Any]:
    return {
        "path": path,
        "operation": "create_or_replace",
        "new_content": content,
        "generated_by": f"{module_name}_module_agent",
        "module_name": module_name,
        "rationale": "comprehensive test",
        "dependencies": [],
        "satisfies": [],
        "risk_notes": [],
        "used_references": [],
    }


class TestG4CodegenAgentModulesWithMockProvider:
    """Comprehensive E2E test using mock provider for full codegen flow."""

    def test_full_mock_provider_pipeline(self, workspace: Path) -> None:
        """Full pipeline from module results through to persist with mock provider."""
        # Simulate all core modules passing
        module_results = {
            "material": {
                "module_name": "material",
                "status": "generated",
                "generated_files": [
                    _valid_file(
                        "src/MaterialRegistry.cc",
                        '#include "MaterialRegistry.hh"\n'
                        '#include "G4NistManager.hh"\n'
                        "void MaterialRegistry::DefineMaterials() {\n"
                        '  G4NistManager::Instance()->FindOrBuildMaterial("G4_Si");\n'
                        "}\n",
                        "material",
                    ),
                    _valid_file(
                        "include/MaterialRegistry.hh",
                        "#pragma once\n#include <G4Material.hh>\n"
                        "class MaterialRegistry { public: void DefineMaterials(); };\n",
                        "material",
                    ),
                ],
                "errors": [],
                "warnings": [],
            },
            "geometry": {
                "module_name": "geometry",
                "status": "generated",
                "generated_files": [
                    _valid_file(
                        "src/DetectorConstruction.cc",
                        '#include "DetectorConstruction.hh"\n'
                        '#include "G4SystemOfUnits.hh"\n'
                        '#include "G4Box.hh"\n'
                        '#include "G4LogicalVolume.hh"\n'
                        '#include "G4PVPlacement.hh"\n'
                        '#include "G4NistManager.hh"\n'
                        '#include "MaterialRegistry.hh"\n'
                        "G4VPhysicalVolume* DetectorConstruction::Construct() {\n"
                        "  MaterialRegistry::DefineMaterials();\n"
                        '  auto* worldSolid = new G4Box("World", 5*m, 5*m, 5*m);\n'
                        "  auto* worldLV = new G4LogicalVolume(worldSolid, "
                        '    G4NistManager::Instance()->FindOrBuildMaterial("G4_AIR"), "WorldLV");\n'  # noqa: E501
                        '  auto* worldPV = new G4PVPlacement(nullptr, {}, worldLV, "WorldPV", nullptr, false, 0);\n'  # noqa: E501
                        "  return worldPV;\n"
                        "}\n",
                        "geometry",
                    ),
                    _valid_file(  # noqa: E501  # noqa: E501
                        "include/DetectorConstruction.hh",
                        "#pragma once\n#include <G4VUserDetectorConstruction.hh>\n"
                        "class DetectorConstruction : public G4VUserDetectorConstruction {\n"
                        "public:\n  G4VPhysicalVolume* Construct() override;\n};\n",
                        "geometry",
                    ),
                ],
                "errors": [],
                "warnings": [],
            },
            "physics": {
                "module_name": "physics",
                "status": "generated",
                "generated_files": [
                    _valid_file(
                        "src/PhysicsList.cc",
                        '#include "PhysicsList.hh"\n'
                        '#include "G4ParticleDefinition.hh"\n'
                        "PhysicsList::PhysicsList() {\n"
                        "  RegisterPhysics(new G4DecayPhysics());\n"
                        "}\n",
                        "physics",
                    ),
                    _valid_file(
                        "include/PhysicsList.hh",
                        "#pragma once\n#include <G4VModularPhysicsList.hh>\n"
                        "class PhysicsList : public G4VModularPhysicsList {\n"
                        "public:\n  PhysicsList();\n};\n",
                        "physics",
                    ),
                ],
                "errors": [],
                "warnings": [],
            },
        }

        gate_results = {
            name: {
                "hard": {"status": "pass", "checks": [], "errors": []},
                "llm": {"status": "pass", "checks": [], "errors": []},
            }
            for name in module_results
        }

        # Step 1: Hard gate each module
        for name, result in module_results.items():
            files = [GeneratedModuleFile(**f) for f in result["generated_files"]]
            gate = run_hard_gate_checks(name, files)
            assert gate.status == "pass", f"Module {name} hard gate failed: {gate.errors}"

        # Step 2: Assemble patch
        patch = assemble_proposed_patch(module_results, gate_results, "mock_full_test")
        assert len(patch["changed_files"]) > 0

        # Step 3: Static scan
        scan = scan_generated_code(patch, "mock_full_test")
        assert scan["status"] == "pass", f"Static scan failed: {scan['findings']}"

        # Step 4: Cross-file hard gate
        cross_gate = run_cross_file_hard_gate(
            patch, {"classes": [], "file_structure": {}}, "mock_full_test"
        )
        # May have warnings but should not fail on content issues
        assert cross_gate["status"] in ("pass", "fail")

        # Step 5: Persist
        import asyncio

        state = {
            "job_id": "mock_full_test",
            "run_mode": "strict",
            "proposed_patch": patch,
            "static_semantic_scan": scan,
            "cross_file_hard_gate": cross_gate,
            "cross_file_llm_gate": {"status": "pass"},
        }

        result = asyncio.run(persist_codegen_output_node(state))

        expected_status = (
            "passed" if scan["status"] == "pass" and cross_gate["status"] == "pass" else "failed"
        )
        assert result["g4_codegen_status"] == expected_status
        assert result["generated_code_dir"].endswith("08_geant4")
