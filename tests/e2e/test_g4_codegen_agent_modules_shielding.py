"""E2E test — shielding config codegen pipeline with mock provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent_core.g4_codegen.integration.integration_assembler import assemble_proposed_patch
from agent_core.g4_codegen.scanners.static_semantic_scanner import scan_generated_code
from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
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
        "rationale": "shielding module",
        "dependencies": [],
        "satisfies": [],
        "risk_notes": [],
        "used_references": [],
    }


class TestG4CodegenAgentModulesShielding:
    """E2E test for shielding body config with mock provider."""

    def test_shielding_codegen_pipeline(self, workspace: Path) -> None:
        """Shielding config should produce valid code through the pipeline."""
        module_results = {
            "material": {
                "module_name": "material",
                "status": "generated",
                "generated_files": [
                    _valid_file(
                        "src/MaterialRegistry.cc",
                        '#include "MaterialRegistry.hh"\n'
                        '#include "G4NistManager.hh"\n'
                        'void MaterialRegistry::DefineMaterials() {\n'
                        '  G4NistManager::Instance()->FindOrBuildMaterial("G4_Pb");\n'
                        '  G4NistManager::Instance()->FindOrBuildMaterial("G4_CONCRETE");\n'
                        '}\n',
                        "material",
                    ),
                    _valid_file(
                        "include/MaterialRegistry.hh",
                        '#pragma once\n#include <G4Material.hh>\n'
                        'class MaterialRegistry { public: void DefineMaterials(); };\n',
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
                        "src/ShieldingConstruction.cc",
                        '#include "ShieldingConstruction.hh"\n'
                        '#include "G4SystemOfUnits.hh"\n'
                        '#include "G4Box.hh"\n'
                        '#include "G4LogicalVolume.hh"\n'
                        '#include "G4PVPlacement.hh"\n'
                        '#include "G4NistManager.hh"\n'
                        'G4VPhysicalVolume* ShieldingConstruction::Construct() {\n'
                        '  auto* worldSolid = new G4Box("World", 5000*cm, 5000*cm, 5000*cm);\n'
                        '  auto* worldLV = new G4LogicalVolume(worldSolid, '
                        '    G4NistManager::Instance()->FindOrBuildMaterial("G4_AIR"), "WorldLV");\n'
                        '  auto* worldPV = new G4PVPlacement(nullptr, {}, worldLV, "WorldPV", nullptr, false, 0);\n'
                        '  return worldPV;\n'
                        '}\n',
                        "geometry",
                    ),
                    _valid_file(
                        "include/ShieldingConstruction.hh",
                        '#pragma once\n#include <G4VUserDetectorConstruction.hh>\n'
                        'class ShieldingConstruction : public G4VUserDetectorConstruction {\n'
                        'public:\n  G4VPhysicalVolume* Construct() override;\n};\n',
                        "geometry",
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

        # Assemble
        patch = assemble_proposed_patch(module_results, gate_results, "shield_e2e")
        assert len(patch["changed_files"]) > 0

        # Verify Pb and concrete materials are referenced
        all_content = " ".join(
            f["new_content"] for f in patch["changed_files"]
        )
        assert "G4_Pb" in all_content or "G4_CONCRETE" in all_content

        # Hard gate
        for name, result in module_results.items():
            files = [GeneratedModuleFile(**f) for f in result["generated_files"]]
            gate = run_hard_gate_checks(name, files)
            assert gate.status == "pass", f"Module {name} failed: {gate.errors}"

        # Static scan
        scan = scan_generated_code(patch, "shield_e2e")
        assert scan["status"] == "pass", f"Static scan failed: {scan['findings']}"
