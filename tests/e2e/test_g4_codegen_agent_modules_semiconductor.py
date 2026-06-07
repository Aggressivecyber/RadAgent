"""E2E test — semiconductor detector config codegen pipeline with mock provider."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

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


def _semiconductor_model_ir() -> dict[str, Any]:
    return {
        "model_ir_id": "semi_test",
        "job_id": "semi_e2e",
        "modeling_mode": "realistic",
        "target_system": "Silicon Semiconductor Detector",
        "components": [
            {
                "component_id": "world",
                "display_name": "World Volume",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 5000, "dy": 5000, "dz": 5000},
                "material_id": "G4_AIR",
                "roles": [],
                "open_issues": [],
                "source_evidence": [],
            },
            {
                "component_id": "silicon_det",
                "display_name": "Silicon Detector",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 100, "dy": 100, "dz": 50},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "roles": ["edep_region"],
                "open_issues": [],
                "source_evidence": [],
            },
        ],
        "materials": [
            {"material_id": "G4_AIR", "name": "G4_AIR", "classification": "nist"},
            {"material_id": "G4_Si", "name": "G4_Si", "classification": "nist"},
        ],
        "sources": [
            {"source_id": "proton", "particle_type": "proton", "energy": "100 MeV"},
        ],
        "physics": {"physics_list": "FTFP_BERT"},
        "scoring": [
            {"scoring_id": "edep", "scoring_type": "region"},
        ],
    }


def _valid_file(path: str, content: str, module_name: str) -> dict[str, Any]:
    return {
        "path": path,
        "operation": "create_or_replace",
        "new_content": content,
        "generated_by": f"{module_name}_module_agent",
        "module_name": module_name,
        "rationale": "test",
        "dependencies": [],
        "satisfies": [],
        "risk_notes": [],
        "used_references": [],
    }


class TestG4CodegenAgentModulesSemiconductor:
    """E2E test for semiconductor detector with mock provider."""

    def test_full_codegen_pipeline_semiconductor(self, workspace: Path) -> None:
        """Full pipeline: assemble → scan → hard gate for semiconductor config."""
        # Simulate module outputs
        module_results = {
            "material": {
                "module_name": "material",
                "status": "generated",
                "generated_files": [
                    _valid_file(
                        "src/MaterialRegistry.cc",
                        '#include "MaterialRegistry.hh"\n#include "G4NistManager.hh"\n'
                        'void MaterialRegistry::DefineMaterials() {\n'
                        '  G4NistManager::Instance()->FindOrBuildMaterial("G4_AIR");\n'
                        '  G4NistManager::Instance()->FindOrBuildMaterial("G4_Si");\n'
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
                        "src/DetectorConstruction.cc",
                        '#include "DetectorConstruction.hh"\n'
                        '#include "G4SystemOfUnits.hh"\n'
                        '#include "G4Box.hh"\n'
                        '#include "G4LogicalVolume.hh"\n'
                        '#include "G4PVPlacement.hh"\n'
                        '#include "G4NistManager.hh"\n'
                        'G4VPhysicalVolume* DetectorConstruction::Construct() {\n'
                        '  auto* worldSolid = new G4Box("World", 5000*cm, 5000*cm, 5000*cm);\n'
                        '  auto* worldLV = new G4LogicalVolume(worldSolid, G4NistManager::Instance()->FindOrBuildMaterial("G4_AIR"), "WorldLV");\n'
                        '  auto* worldPV = new G4PVPlacement(nullptr, {}, worldLV, "WorldPV", nullptr, false, 0);\n'
                        '  return worldPV;\n'
                        '}\n',
                        "geometry",
                    ),
                    _valid_file(
                        "include/DetectorConstruction.hh",
                        '#pragma once\n#include <G4VUserDetectorConstruction.hh>\n'
                        'class DetectorConstruction : public G4VUserDetectorConstruction {\n'
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

        # Step 1: Assemble patch
        patch = assemble_proposed_patch(module_results, gate_results, "semi_e2e")
        assert len(patch["changed_files"]) > 0

        # Step 2: Run hard gate on each module
        for name, result in module_results.items():
            files = [GeneratedModuleFile(**f) for f in result["generated_files"]]
            gate = run_hard_gate_checks(name, files)
            assert gate.status == "pass", f"Module {name} hard gate failed: {gate.errors}"

        # Step 3: Static scan
        scan = scan_generated_code(patch, "semi_e2e")
        assert scan["status"] == "pass", f"Static scan failed: {scan['findings']}"

    def test_patch_files_written_to_workspace(self, workspace: Path) -> None:
        """Patch files should be persisted in the job workspace."""
        module_results = {
            "material": {
                "module_name": "material",
                "status": "generated",
                "generated_files": [
                    _valid_file("src/Mat.cc", "// material code", "material"),
                ],
                "errors": [],
                "warnings": [],
            },
        }
        gate_results = {
            "material": {
                "hard": {"status": "pass"},
                "llm": {"status": "pass"},
            },
        }

        patch = assemble_proposed_patch(module_results, gate_results, "semi_write")

        # Verify patch was persisted
        from agent_core.config.workspace import get_job_dir
        codegen_dir = get_job_dir("semi_write") / "06_codegen"
        patch_path = codegen_dir / "proposed_patch.json"
        assert patch_path.exists()

        saved = json.loads(patch_path.read_text())
        assert saved["patch_id"] == patch["patch_id"]
