from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agent_core.g4_codegen import global_integration_agent as gia
from agent_core.g4_codegen.global_integration_agent import run_global_integration_agent
from agent_core.g4_codegen.graph_nodes import (
    GLOBAL_INTEGRATION_RUNTIME_REPAIR_ROUNDS,
    global_integration_agent_node,
)
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier
from agent_core.workspace.paths import STAGE_CODEGEN


def _patch() -> dict[str, Any]:
    return {
        "changed_files": [
            {
                "path": "include/DetectorConstruction.hh",
                "operation": "create_or_replace",
                "new_content": "#pragma once\nclass DetectorConstruction {};\n",
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            },
            {
                "path": "main.cc",
                "operation": "create_or_replace",
                "new_content": "int main() { return 0; }\n",
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
        ],
    }


def test_global_integration_normalizes_new_file_metadata() -> None:
    candidate = {
        "changed_files": [
            {
                "path": "macros/scoring.mac",
                "new_content": "/score/create/boxMesh mesh\n",
            }
        ]
    }

    normalized = gia._normalize_candidate_patch_metadata(_patch(), candidate)

    entry = normalized["changed_files"][0]
    assert entry["zone"] == "runtime_macro"
    assert entry["generated_by"] == "global_integration_agent"
    assert entry["module_name"] == "runtime_app"
    assert entry["operation"] == "create_or_replace"


def test_global_integration_model_context_remains_valid_json_when_over_budget() -> None:
    oversized_project = {
        "path": "src/Oversized.cc",
        "new_content": "void f() {\n" + ("  // generated code keeps going\n" * 500),
        "module_name": "simulation_core",
        "generated_by": "simulation_core_module_agent",
    }
    context = {
        "job_id": "json_budget",
        "available_modules": ["simulation_core", "runtime_app"],
        "project_files": [oversized_project],
        "runtime_failure_context": {
            "status": "fail",
            "errors": ["BUILD_ERROR_SENTINEL: compile failed"],
        },
        "database_search": {},
        "web_search": {},
        "interface_contracts": {"huge": "x" * 4_000},
        "module_contracts": {"huge": "y" * 4_000},
        "module_context_summaries": {"huge": {"interface_context": "z" * 4_000}},
        "integration_memory": {"previous_runtime_gate": {"errors": ["old failure"]}},
        "write_contract": {"must_preserve_schema": True},
    }

    text = gia._model_context_json(
        context,
        max_chars=2_000,
        max_project_file_chars=20_000,
    )

    parsed = json.loads(text)
    assert parsed["runtime_failure_context"]["errors"] == [
        "BUILD_ERROR_SENTINEL: compile failed"
    ]
    assert isinstance(parsed["project_files"], list)
    assert len(text) <= 2_000


def test_global_integration_qualifies_hit_type_in_sensitive_detector_patch() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/SensitiveDetector.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "SensitiveDetector.hh"\n'
                    '#include "Hit.hh"\n'
                    "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                    "    G4double edep = step->GetTotalEnergyDeposit();\n"
                    "    if (edep == 0.) return false;\n"
                    "    Hit* hit = new Hit();\n"
                    "    fHitsCollection->insert(hit);\n"
                    "    return true;\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            }
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": "src/SensitiveDetector.cc",
                "new_content": (
                    '#include "SensitiveDetector.hh"\n'
                    '#include "Hit.hh"\n'
                    "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                    "    G4double edep = step->GetTotalEnergyDeposit();\n"
                    "    if (edep == 0.) return false;\n"
                    "    Hit* hit = new Hit();\n"
                    "    fHitsCollection->insert(hit);\n"
                    "    return true;\n"
                    "}\n"
                ),
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert "::Hit* hit = new ::Hit();" in content
    assert "Hit* hit = new Hit();" not in content
    assert "edep == 0.0" in content


def test_global_integration_normalizes_scoring_manager_reference_api() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/SteppingAction.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "ScoringManager.hh"\n'
                    "void SteppingAction::UserSteppingAction(const G4Step* step) {\n"
                    "  G4double edep = step->GetTotalEnergyDeposit();\n"
                    "  ScoringManager::Instance()->RecordEnergyDeposit(edep, 0.0);\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
            {
                "path": "include/ScoringManager.hh",
                "operation": "create_or_replace",
                "new_content": (
                    "#pragma once\n"
                    "class ScoringManager {\n"
                    " public:\n"
                    "  static ScoringManager& Instance();\n"
                    "  void RecordEnergyDeposit(double edep);\n"
                    "};\n"
                ),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            }
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": "src/SteppingAction.cc",
                "new_content": original_patch["changed_files"][0]["new_content"],
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert "ScoringManager::Instance().RecordEnergyDeposit(edep);" in content
    assert "ScoringManager::Instance()->RecordEnergyDeposit(edep, 0.0);" not in content


def test_global_integration_preserves_pointer_scoring_manager_api() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/SteppingAction.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "ScoringManager.hh"\n'
                    "void SteppingAction::UserSteppingAction(const G4Step* step) {\n"
                    "  G4double edep = step->GetTotalEnergyDeposit();\n"
                    "  ScoringManager::Instance()->RecordEnergyDeposit(edep, 0.0);\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
            {
                "path": "include/ScoringManager.hh",
                "operation": "create_or_replace",
                "new_content": (
                    "#pragma once\n"
                    "class ScoringManager {\n"
                    " public:\n"
                    "  static ScoringManager* Instance();\n"
                    "  void RecordEnergyDeposit(double edep, double dose);\n"
                    "};\n"
                ),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            },
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": "src/SteppingAction.cc",
                "new_content": original_patch["changed_files"][0]["new_content"],
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert "ScoringManager::Instance()->RecordEnergyDeposit(edep, 0.0);" in content


def test_global_integration_uses_serial_run_manager_for_generated_main() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "main.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "G4RunManagerFactory.hh"\n'
                    "int main() {\n"
                    "  auto* runManager =\n"
                    "      G4RunManagerFactory::CreateRunManager(G4RunManagerType::Default);\n"
                    "  delete runManager;\n"
                    "  return 0;\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            }
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": "main.cc",
                "new_content": original_patch["changed_files"][0]["new_content"],
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert "G4RunManagerType::Serial" in content
    assert "G4RunManagerType::Default" not in content


def test_global_integration_wires_scoring_volume_and_avoids_duplicate_step_scoring() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/DetectorConstruction.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "DetectorConstruction.hh"\n'
                    '#include "SensitiveDetector.hh"\n'
                    "void DetectorConstruction::AttachSensitiveDetectors()\n"
                    "{\n"
                    "    G4LogicalVolume* si_lv = fPlacementManager->GetLogicalVolume("
                    '"silicon_detector");\n'
                    '    auto* sd = new SensitiveDetector("SensitiveDetector", "SiliconHits");\n'
                    "    G4SDManager::GetSDMpointer()->AddNewDetector(sd);\n"
                    "    SetSensitiveDetector(si_lv, sd);\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            },
            {
                "path": "src/SensitiveDetector.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "SensitiveDetector.hh"\n'
                    '#include "ScoringManager.hh"\n'
                    "G4bool SensitiveDetector::ProcessHits(G4Step* step, G4TouchableHistory*) {\n"
                    "    G4double edep = step->GetTotalEnergyDeposit();\n"
                    "    fScoringManager->RecordEnergyDeposit(edep);\n"
                    "    return true;\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            },
            {
                "path": "src/SteppingAction.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "SteppingAction.hh"\n'
                    '#include "ScoringManager.hh"\n'
                    '#include "OutputManager.hh"\n'
                    "void SteppingAction::UserSteppingAction(const G4Step* step)\n"
                    "{\n"
                    "  if (fScoringVolume == nullptr) {\n"
                    "    auto* store = G4LogicalVolumeStore::GetInstance();\n"
                    '    auto it = store->GetVolume("silicon_detector_LV");\n'
                    "    if (it != nullptr) {\n"
                    "      fScoringVolume = it;\n"
                    "    }\n"
                    "  }\n"
                    "  G4double edep = step->GetTotalEnergyDeposit();\n"
                    "  ScoringManager::Instance().RecordEnergyDeposit(edep);\n"
                    "  OutputManager::Instance()->Record3DHit("
                    "step->GetPreStepPoint()->GetPosition(), edep / MeV);\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
            {
                "path": "include/ScoringManager.hh",
                "operation": "create_or_replace",
                "new_content": (
                    "#pragma once\n"
                    "class G4LogicalVolume;\n"
                    "class ScoringManager {\n"
                    " public:\n"
                    "  static ScoringManager& Instance();\n"
                    "  void Initialize(G4LogicalVolume* scoringVolume);\n"
                    "  void RecordEnergyDeposit(double edep);\n"
                    "};\n"
                ),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            },
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": item["path"],
                "new_content": item["new_content"],
            }
            for item in original_patch["changed_files"]
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    by_path = {item["path"]: item["new_content"] for item in repaired["changed_files"]}
    detector_content = by_path["src/DetectorConstruction.cc"]
    stepping_content = by_path["src/SteppingAction.cc"]
    assert '#include "ScoringManager.hh"' in detector_content
    assert "ScoringManager::Instance().Initialize(si_lv);" in detector_content
    assert '"SiliconDetector"' in stepping_content
    assert "silicon_detector_LV" not in stepping_content
    assert "ScoringManager::Instance().RecordEnergyDeposit(edep);" not in stepping_content
    assert "OutputManager::Instance()->Record3DHit" in stepping_content


def test_global_integration_aligns_physics_list_to_confirmed_ir() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/PhysicsListFactoryWrapper.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "PhysicsListFactoryWrapper.hh"\n'
                    '#include "G4PhysListFactory.hh"\n'
                    "G4VUserPhysicsList* PhysicsListFactoryWrapper::CreatePhysicsList()\n"
                    "{\n"
                    "  G4PhysListFactory factory;\n"
                    '  auto* physicsList = factory.GetReferencePhysList("QGSP_BIC");\n'
                    "  return physicsList;\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "beam_physics_module_agent",
                "module_name": "beam_physics",
                "rationale": "test",
            },
            {
                "path": "macros/physics_list.mac",
                "operation": "create_or_replace",
                "new_content": "/physics_list/select FTFP_BERT\n",
                "zone": "runtime_macro",
                "generated_by": "beam_physics_module_agent",
                "module_name": "beam_physics",
                "rationale": "test",
            }
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": "src/PhysicsListFactoryWrapper.cc",
                "new_content": original_patch["changed_files"][0]["new_content"],
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert 'GetReferencePhysList("FTFP_BERT")' in content
    assert "QGSP_BIC" not in content


def test_global_integration_aligns_provenance_physics_list_to_confirmed_ir() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/OutputManager.cc",
                "operation": "create_or_replace",
                "new_content": (
                    "void OutputManager::WriteProvenance()\n"
                    "{\n"
                    "  ofs << \"  \\\"physics_list\\\": \\\"QGSP_BIC\\\",\" << std::endl;\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
            {
                "path": "macros/physics_list.mac",
                "operation": "create_or_replace",
                "new_content": "/physics_list/select FTFP_BERT\n",
                "zone": "runtime_macro",
                "generated_by": "beam_physics_module_agent",
                "module_name": "beam_physics",
                "rationale": "test",
            },
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": "src/OutputManager.cc",
                "new_content": original_patch["changed_files"][0]["new_content"],
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert '\\"physics_list\\": \\"FTFP_BERT\\"' in content
    assert "QGSP_BIC" not in content


def test_global_integration_aligns_run_macro_energy_to_primary_generator() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/PrimaryGeneratorAction.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "PrimaryGeneratorAction.hh"\n'
                    "PrimaryGeneratorAction::PrimaryGeneratorAction() {\n"
                    "  fParticleGun->SetParticleEnergy(10.0 * MeV);\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "beam_physics_module_agent",
                "module_name": "beam_physics",
                "rationale": "test",
            },
            {
                "path": "macros/run.mac",
                "operation": "create_or_replace",
                "new_content": (
                    "/run/initialize\n"
                    "/gun/particle proton\n"
                    "/gun/energy 100 MeV\n"
                    "/gun/direction 0 0 1\n"
                    "/run/beamOn 10\n"
                ),
                "zone": "runtime_macro",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": item["path"],
                "new_content": item["new_content"],
            }
            for item in original_patch["changed_files"]
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    run_macro = next(
        item["new_content"]
        for item in repaired["changed_files"]
        if item["path"] == "macros/run.mac"
    )
    assert "/gun/energy 10.0 MeV" in run_macro
    assert "/gun/energy 100 MeV" not in run_macro


def test_global_integration_normalizes_real_g4_ir_units_and_run_events() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/DetectorConstruction.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "DetectorConstruction.hh"\n'
                    "void DetectorConstruction::BuildGeometry() {\n"
                    "  const G4double world_hx = 100.0 * cm;\n"
                    '  G4Box* si_solid = new G4Box("SiliconDetector", '
                    "10.0 * cm, 10.0 * cm, 0.25 * cm);\n"
                    '  G4Box* oxide_solid = new G4Box("OxideLayer", '
                    "10.0 * cm, 10.0 * cm, 0.01 * cm);\n"
                    "  G4ThreeVector(0.0, 0.0, 0.27 * cm);\n"
                    '  G4Box* al_solid = new G4Box("AluminumShield", '
                    "15.0 * cm, 15.0 * cm, 0.5 * cm);\n"
                    "  G4ThreeVector(0.0, 0.0, -10.0 * cm);\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            },
            {
                "path": "src/PrimaryGeneratorAction.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "PrimaryGeneratorAction.hh"\n'
                    "PrimaryGeneratorAction::PrimaryGeneratorAction() {\n"
                    "  fParticleGun->SetParticleEnergy(10.0 * MeV);\n"
                    "  fParticleGun->SetParticlePosition(G4ThreeVector(0.0, 0.0, -80.0 * cm));\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "beam_physics_module_agent",
                "module_name": "beam_physics",
                "rationale": "test",
            },
            {
                "path": "src/PhysicsListFactoryWrapper.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "PhysicsListFactoryWrapper.hh"\n'
                    "G4VUserPhysicsList* PhysicsListFactoryWrapper::CreatePhysicsList() {\n"
                    '  auto* physicsList = factory.GetReferencePhysList("FTFP_BERT");\n'
                    "  physicsList->SetDefaultCutValue(1.0 * mm);\n"
                    "  return physicsList;\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "beam_physics_module_agent",
                "module_name": "beam_physics",
                "rationale": "test",
            },
            {
                "path": "macros/run.mac",
                "operation": "create_or_replace",
                "new_content": (
                    "/run/initialize\n"
                    "/gun/particle proton\n"
                    "/gun/energy 100 MeV\n"
                    "/gun/position 0 0 -20 cm\n"
                    "/gun/direction 0 0 1\n"
                    "/run/beamOn 10\n"
                ),
                "zone": "runtime_macro",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": item["path"],
                "new_content": item["new_content"],
            }
            for item in original_patch["changed_files"]
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    by_path = {item["path"]: item["new_content"] for item in repaired["changed_files"]}
    detector = by_path["src/DetectorConstruction.cc"]
    primary = by_path["src/PrimaryGeneratorAction.cc"]
    physics = by_path["src/PhysicsListFactoryWrapper.cc"]
    run_macro = by_path["macros/run.mac"]
    assert "* cm" not in detector
    assert "100.0 * mm" in detector
    assert "0.25 * mm" in detector
    assert "0.27 * mm" in detector
    assert "-10.0 * mm" in detector
    assert "SetParticlePosition(G4ThreeVector(0.0, 0.0, -80.0 * mm))" in primary
    assert "SetDefaultCutValue(0.1 * mm)" in physics
    assert "/gun/energy 10.0 MeV" in run_macro
    assert "/gun/position 0 0 -80.0 mm" in run_macro
    assert "/run/beamOn 1000" in run_macro


def test_global_integration_writes_summary_events_requested_from_total_events() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/OutputManager.cc",
                "operation": "create_or_replace",
                "new_content": (
                    "void OutputManager::WriteSummary(G4int totalEvents)\n"
                    "{\n"
                    "  ofs << \"{\" << std::endl;\n"
                    "  ofs << \"  \\\"total_events\\\": \" << totalEvents << \",\" << std::endl;\n"
                    "  ofs << \"  \\\"total_edep_MeV\\\": \" << totalEdep << std::endl;\n"
                    "  ofs << \"}\" << std::endl;\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            }
        ]
    }
    candidate_patch = {
        "changed_files": [
            {
                "path": "src/OutputManager.cc",
                "new_content": original_patch["changed_files"][0]["new_content"],
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, candidate_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert '\\"events_requested\\": ' in content
    assert "totalEvents << \",\"" in content


def test_global_integration_postprocesses_generated_code_for_no_magic_number_gate() -> None:
    from agent_core.g4_codegen.validators.no_magic_number import check_magic_numbers

    output_manager = (
        '#include "OutputManager.hh"\n'
        "void OutputManager::Record3DHit(const G4ThreeVector& pos, G4double edepMeV) {\n"
        "  G4int ix = static_cast<G4int>(std::floor((pos.x() + 100.0) / kBinSizeXY));\n"
        "  G4int iz = static_cast<G4int>(std::floor((pos.z() + 2.5) / kBinSizeZ));\n"
        "  ofs << std::scientific << std::setprecision(6) << edepMeV;\n"
        "  char timeStr[64];\n"
        '  ofs << "  \\"version\\": \\"11.3\\"," << std::endl;\n'
        "}\n"
    )
    hit = (
        '#include "Hit.hh"\n'
        "void Hit::Draw() { circle.SetScreenSize(5.); }\n"
        'void Hit::Print() { G4cout << std::setw(7) << fTrackID; }\n'
    )
    detector = (
        '#include "DetectorConstruction.hh"\n'
        "void DetectorConstruction::BuildGeometry() {\n"
        "  G4VisAttributes al_vis(G4Colour(0.6, 0.6, 0.6));\n"
        "}\n"
    )
    main = (
        "int main() {\n"
        "  G4int precision = 4;\n"
        "  G4SteppingVerbose::UseBestUnit(precision);\n"
        "}\n"
    )
    scoring_hh = (
        "class ScoringManager {\n"
        "  G4double fVolume = 0.0;  // in cm^3\n"
        "  G4double fDensity = 0.0; // in g/cm^3\n"
        "};\n"
    )
    scoring_cc = (
        "void ScoringManager::Initialize() {\n"
        "  fVolume /= (cm * cm * cm); // convert to cm^3\n"
        "  fDensity = x / (g / cm3); // g/cm^3\n"
        "  fOutputFile << std::setprecision(6);\n"
        "}\n"
    )
    original_patch = {
        "changed_files": [
            {"path": "src/OutputManager.cc", "new_content": output_manager},
            {"path": "src/Hit.cc", "new_content": hit},
            {"path": "src/DetectorConstruction.cc", "new_content": detector},
            {"path": "main.cc", "new_content": main},
            {"path": "include/ScoringManager.hh", "new_content": scoring_hh},
            {"path": "src/ScoringManager.cc", "new_content": scoring_cc},
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, original_patch)

    assert errors == []
    by_path = {entry["path"]: entry["new_content"] for entry in repaired["changed_files"]}
    assert "constexpr int kCsvPrecision = 6;" in by_path["src/ScoringManager.cc"]
    for entry in repaired["changed_files"]:
        clean, violations = check_magic_numbers(entry["new_content"], entry["path"])
        assert clean, violations


class _Profile:
    provider = ModelProvider.OPENAI_COMPATIBLE
    model_name = "unit-test-model"


class _MockProfile:
    provider = ModelProvider.MOCK
    model_name = "mock"


class _Gateway:
    def __init__(self, response: dict[str, Any], *, mock: bool = False) -> None:
        self.response = response
        self.prompts: list[str] = []
        self.call_kwargs: list[dict[str, Any]] = []
        self.profiles = {ModelTier.MAX: _MockProfile() if mock else _Profile()}

    async def call(self, **kwargs: Any) -> ModelCallResult:
        self.call_kwargs.append(kwargs)
        self.prompts.append(str(kwargs["user_prompt"]))
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content=json.dumps(self.response),
            parsed_json=self.response,
            usage={},
        )


class _SequenceGateway:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.call_kwargs: list[dict[str, Any]] = []
        self.profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **kwargs: Any) -> ModelCallResult:
        self.call_kwargs.append(kwargs)
        self.prompts.append(str(kwargs["user_prompt"]))
        response = self.responses.pop(0)
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content=json.dumps(response),
            parsed_json=response,
            usage={},
        )


class _InitialThenErrorGateway:
    def __init__(self, response: dict[str, Any], *, error: str) -> None:
        self.response = response
        self.error = error
        self.calls = 0
        self.profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **_kwargs: Any) -> ModelCallResult:
        self.calls += 1
        if self.calls == 1:
            return ModelCallResult(
                task=ModelTask.CODEGEN,
                tier=ModelTier.MAX,
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="unit-test-model",
                content=json.dumps(self.response),
                parsed_json=self.response,
                usage={},
            )
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content="",
            parsed_json=None,
            usage={},
            error=self.error,
        )


class _ErrorGateway:
    def __init__(self, *, error: str) -> None:
        self.error = error
        self.prompts: list[str] = []
        self.call_kwargs: list[dict[str, Any]] = []
        self.profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **kwargs: Any) -> ModelCallResult:
        self.call_kwargs.append(kwargs)
        self.prompts.append(str(kwargs["user_prompt"]))
        return ModelCallResult(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="unit-test-model",
            content="",
            parsed_json=None,
            usage={},
            error=self.error,
        )


class _FailIfCalledGateway:
    profiles = {ModelTier.MAX: _Profile()}

    async def call(self, **_kwargs: Any) -> ModelCallResult:
        raise AssertionError("initial global integration model call should be deferred")


async def _database_evidence(_query: str) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": "g4-run-manager",
            "title": "Geant4 Run Manager",
            "content": "G4RunManager wires detector construction and physics list.",
            "source": "database",
            "score": 1.0,
        }
    ]


async def _web_evidence(_query: str) -> list[dict[str, Any]]:
    return [
        {
            "title": "Geant4 application guide",
            "url": "https://geant4-userdoc.web.cern.ch/",
            "snippet": "User initialization classes are registered on the run manager.",
            "source_type": "web",
            "confidence": 0.8,
        }
    ]


async def _empty_evidence(_query: str) -> list[dict[str, Any]]:
    return []


@pytest.mark.asyncio
async def test_global_integration_agent_reads_modules_files_database_and_web(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    response = {
        "status": "integrated",
        "proposed_patch": {
            "changed_files": [
                {
                    "path": "main.cc",
                    "operation": "create_or_replace",
                    "new_content": '#include "DetectorConstruction.hh"\nint main() { return 0; }\n',
                    "zone": "green",
                    "generated_by": "runtime_app_module_agent",
                    "module_name": "runtime_app",
                    "rationale": "wire detector header",
                }
            ]
        },
        "issues_fixed": [{"target": "main.cc", "message": "wired generated header"}],
        "errors": [],
    }
    gateway = _Gateway(response)
    codegen_dir = tmp_path / "jobs" / "global_integration_test" / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True)
    (codegen_dir / "global_integration_agent_report.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "errors": ["previous constructor mismatch"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _web_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_test",
        module_results={"simulation_core": {}, "runtime_app": {}},
        module_contracts={
            "simulation_core": {"output_files": ["include/DetectorConstruction.hh"]},
            "runtime_app": {"output_files": ["main.cc"]},
        },
    )

    assert report["status"] == "passed"
    assert report["changed_files"] == ["main.cc"]
    assert report["capabilities_used"]["database_search"] is True
    assert report["capabilities_used"]["web_search"] is True
    files_by_path = {entry["path"]: entry for entry in repaired["changed_files"]}
    assert set(files_by_path) == {"include/DetectorConstruction.hh", "main.cc"}
    assert '#include "DetectorConstruction.hh"' in files_by_path["main.cc"]["new_content"]
    prompt = gateway.prompts[0]
    assert "available_modules" in prompt
    assert "DetectorConstruction.hh" in prompt
    assert "database_search" in prompt
    assert "web_search" in prompt
    assert "previous constructor mismatch" in prompt
    context_path = (
        Path(tmp_path)
        / "jobs"
        / "global_integration_test"
        / STAGE_CODEGEN
        / "integration"
        / "global_integration_context.json"
    )
    assert context_path.is_file()


@pytest.mark.asyncio
async def test_global_integration_sends_large_initial_context_to_model(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    large_patch = _patch()
    large_patch["changed_files"].append(
        {
            "path": "src/LargeGenerated.cc",
            "operation": "create_or_replace",
            "new_content": "int generated_value = 0;\n" * 4000,
            "zone": "green",
            "generated_by": "large_module_agent",
            "module_name": "large",
            "rationale": "force large initial integration context",
        }
    )
    gateway = _Gateway({"status": "no_change", "proposed_patch": {"changed_files": []}})
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _web_evidence,
    )
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    repaired, report = await run_global_integration_agent(
        large_patch,
        job_id="global_integration_defer_initial",
        module_results={"simulation_core": {}, "runtime_app": {}, "large": {}},
        runtime_repair_rounds=1,
    )

    assert report["status"] == "passed"
    assert "deferred_until_runtime_gate" not in report
    assert runtime_attempts == [1]
    assert len(gateway.prompts) == 1
    assert "LargeGenerated.cc" in gateway.prompts[0]
    assert report["runtime_gate_attempts"][0]["status"] == "pass"
    assert "deferred_until_runtime_gate" not in repaired["metadata"]["global_integration_agent"]
    assert repaired["metadata"]["final_runtime_gate"]["required"] is True


@pytest.mark.asyncio
async def test_large_initial_integration_uses_runtime_observation_for_repair(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    large_patch = _patch()
    large_patch["changed_files"].append(
        {
            "path": "src/LargeGenerated.cc",
            "operation": "create_or_replace",
            "new_content": "int generated_value = 0;\n" * 4000,
            "zone": "green",
            "generated_by": "large_module_agent",
            "module_name": "large",
            "rationale": "force large initial integration context",
        }
    )
    gateway = _SequenceGateway(
        [
            {
                "status": "no_change",
                "proposed_patch": {"changed_files": []},
                "issues_fixed": [],
                "errors": [],
            },
            {
                "status": "integrated",
                "proposed_patch": {
                    "changed_files": [
                        {"path": "main.cc", "new_content": "int main() { return 0; }\n"}
                    ]
                },
                "issues_fixed": [
                    {"target": "main.cc", "message": "repaired from runtime observation"}
                ],
                "errors": [],
            }
        ]
    )
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        if attempt == 1:
            return {
                "status": "fail",
                "attempt": attempt,
                "errors": ["BUILD_ERROR_SENTINEL: Hit must satisfy G4THitsCollection API"],
                "warnings": [],
                "missing_outputs": ["g4_summary.json"],
            }
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    repaired, report = await run_global_integration_agent(
        large_patch,
        job_id="global_integration_defer_runtime_repair",
        module_results={"simulation_core": {}, "runtime_app": {}, "large": {}},
        runtime_repair_rounds=2,
    )

    assert report["status"] == "passed"
    assert runtime_attempts == [1, 2]
    assert len(gateway.prompts) == 2
    assert "initial integration" in gateway.prompts[0]
    assert "LargeGenerated.cc" in gateway.prompts[0]
    assert "runtime repair round 1" in gateway.prompts[1]
    assert "BUILD_ERROR_SENTINEL" in gateway.prompts[1]
    main_entry = next(f for f in repaired["changed_files"] if f["path"] == "main.cc")
    assert "return 0" in main_entry["new_content"]


@pytest.mark.asyncio
async def test_global_integration_agent_rejects_content_field(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    bad_patch = _patch()
    bad_patch["changed_files"][0]["content"] = "forbidden"
    response = {
        "status": "integrated",
        "proposed_patch": bad_patch,
        "issues_fixed": [],
        "errors": [],
    }
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway(response),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_bad_schema",
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert repaired == _patch()
    assert report["status"] == "failed"
    assert any("content field is forbidden" in error for error in report["errors"])


@pytest.mark.asyncio
async def test_global_integration_agent_partial_patch_inherits_file_metadata(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    response = {
        "status": "integrated",
        "proposed_patch": {
            "changed_files": [
                {
                    "path": "main.cc",
                    "new_content": '#include "DetectorConstruction.hh"\nint main() { return 0; }\n',
                }
            ]
        },
        "issues_fixed": [{"target": "main.cc", "message": "minimal partial edit"}],
        "errors": [],
    }
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway(response),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_partial_metadata",
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert report["status"] == "passed"
    main_entry = next(f for f in repaired["changed_files"] if f["path"] == "main.cc")
    assert main_entry["zone"] == "green"
    assert main_entry["generated_by"] == "runtime_app_module_agent"
    assert main_entry["module_name"] == "runtime_app"


@pytest.mark.asyncio
async def test_global_integration_agent_continues_when_external_evidence_unavailable(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway({"status": "no_change", "proposed_patch": _patch()}),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_no_evidence",
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert report["status"] == "passed"
    assert any("evidence were unavailable" in item for item in report["warnings"])


@pytest.mark.asyncio
async def test_global_integration_accepts_empty_patch_for_no_change(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway({"status": "no_change", "proposed_patch": {"changed_files": []}}),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_no_change_empty_patch",
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert report["status"] == "passed"
    assert report["changed_files"] == []
    assert repaired["changed_files"] == _patch()["changed_files"]


@pytest.mark.asyncio
async def test_global_integration_prompt_keeps_files_and_runtime_observation_first(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    gateway = _Gateway({"status": "no_change", "proposed_patch": _patch()})
    build_result = tmp_path / "build_result.json"
    build_result.write_text(
        json.dumps(
            {
                "success": False,
                "errors": "BUILD_ERROR_SENTINEL: constructor mismatch",
                "stderr": "DetectorConstruction.cc failed to compile",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_prompt_budget",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_failure_context={
            "job_id": "global_integration_prompt_budget",
            "status": "failed",
            "phase": "gate_validation",
            "errors": ["Missing C++ standard setting (CXX_STANDARD or c++17)"],
            "details": {
                "failed_gates": [
                    {
                        "gate_id": 6,
                        "name": "Build/Parse",
                        "status": "fail",
                        "failed_items": ["Build failed"],
                        "message": "Build failed",
                        "file_paths": [str(build_result)],
                    }
                ]
            },
        },
    )

    assert report["status"] == "passed"
    prompt = gateway.prompts[0]
    assert '"project_files"' in prompt
    assert '"runtime_failure_context"' in prompt
    assert "class DetectorConstruction" in prompt
    assert "BUILD_ERROR_SENTINEL" in prompt
    assert "G4-G No Magic Number" not in gia.GLOBAL_INTEGRATION_SYSTEM_PROMPT
    assert "No Magic Number" not in prompt
    assert prompt.find('"runtime_failure_context"') < prompt.find('"project_files"')
    assert gateway.call_kwargs[0]["max_tokens"] == gia.RUNTIME_REPAIR_MAX_TOKENS
    assert gateway.call_kwargs[0]["metadata"]["enable_thinking"] is True


@pytest.mark.asyncio
async def test_initial_global_integration_timeout_continues_to_runtime_gate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    gateway = _ErrorGateway(error="Model call timed out after 365.0s")
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_initial_timeout_runtime_fallback",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_repair_rounds=1,
    )

    assert report["status"] == "passed"
    assert report["errors"] == []
    assert runtime_attempts == [1]
    assert report["runtime_gate_attempts"][0]["status"] == "pass"
    assert "Initial global integration model call failed" in report["warnings"][0]
    assert report["llm_status"] == "initial_model_error_runtime_fallback"
    assert repaired["metadata"]["global_integration_agent"]["runtime_gate_required"] is True
    assert gateway.call_kwargs[0]["max_tokens"] == gia.INITIAL_INTEGRATION_MAX_TOKENS
    assert gateway.call_kwargs[0]["metadata"]["enable_thinking"] is True


@pytest.mark.asyncio
async def test_runtime_observation_model_timeout_still_fails(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    gateway = _ErrorGateway(error="Model call timed out after 365.0s")

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_runtime_timeout_still_fails",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_failure_context={"status": "fail", "errors": ["real build failed"]},
        runtime_repair_rounds=1,
    )

    assert report["status"] == "failed"
    assert report["runtime_gate_attempts"] == []
    assert report["errors"] == [
        "Global integration model call failed: Model call timed out after 365.0s"
    ]
    assert gateway.call_kwargs[0]["max_tokens"] == gia.RUNTIME_REPAIR_MAX_TOKENS
    assert gateway.call_kwargs[0]["metadata"]["enable_thinking"] is True


def test_global_integration_runtime_gate_ignores_magic_number_style(tmp_path) -> None:
    project_dir = tmp_path / "geant4_project"
    output_dir = tmp_path / "g4_output_package"
    src_dir = project_dir / "src"
    src_dir.mkdir(parents=True)
    output_dir.mkdir()
    (src_dir / "OutputManager.cc").write_text(
        "#include <array>\n"
        "void f() {\n"
        "  std::array<int, 3> nBins = {10, 10, 10};\n"
        "}\n",
        encoding="utf-8",
    )
    (output_dir / "g4_summary.json").write_text(
        json.dumps({"job_id": "style", "events_requested": 2}),
        encoding="utf-8",
    )
    (output_dir / "provenance.json").write_text(
        json.dumps({"job_id": "style"}),
        encoding="utf-8",
    )
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.25,0.01\n1,0.50,0.004\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,1.25\n1,0,0,0.50\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n1,0,0,0.004\n",
        encoding="utf-8",
    )
    (output_dir / "smoke_simulation_result.json").write_text(
        json.dumps({"success": True, "errors": ""}),
        encoding="utf-8",
    )

    gate = gia._summarize_runtime_gate_result(
        result={"success": True, "warnings": []},
        attempt=1,
        project_dir=project_dir,
        output_dir=output_dir,
    )

    assert gate["status"] == "pass"
    assert gate["errors"] == []


@pytest.mark.asyncio
async def test_integration_runtime_gate_uses_1000_event_self_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    seen: dict[str, Any] = {}

    class FakeRunner:
        geant4_available = True

        async def smoke_test(
            self,
            project_dir: str,
            *,
            job_id: str = "unknown",
            output_dir: str | None = None,
            events: int = 10,
        ) -> dict[str, Any]:
            seen["events"] = events
            assert events == 1000
            out = Path(str(output_dir))
            out.mkdir(parents=True, exist_ok=True)
            (out / "g4_summary.json").write_text(
                json.dumps({"job_id": job_id, "events_requested": events}),
                encoding="utf-8",
            )
            (out / "provenance.json").write_text(
                json.dumps({"job_id": job_id, "source": "program"}),
                encoding="utf-8",
            )
            (out / "event_table.csv").write_text(
                "EventID,edep_MeV,dose_Gy\n"
                + "\n".join(f"{i},1.0,0.01" for i in range(events))
                + "\n",
                encoding="utf-8",
            )
            (out / "edep_3d.csv").write_text("x,y,z,edep_MeV\n0,0,0,1.0\n", encoding="utf-8")
            (out / "dose_3d.csv").write_text("x,y,z,dose_Gy\n0,0,0,0.01\n", encoding="utf-8")
            return {
                "success": True,
                "cmake_configure_result": {"success": True},
                "build_result": {"success": True},
                "unit_test_result": {"success": True},
                "warnings": [],
            }

    monkeypatch.setattr("agent_core.tools.geant4_runner.Geant4Runner", FakeRunner)

    gate = await gia._run_integration_runtime_gate(
        job_id="runtime_gate_1000",
        proposed_patch=_patch(),
        attempt=1,
    )

    assert seen["events"] == 1000
    assert gate["status"] == "pass"
    assert gate["expected_events"] == 1000


def test_global_integration_runtime_gate_rejects_empty_zero_smoke_outputs(tmp_path) -> None:
    project_dir = tmp_path / "geant4_project"
    output_dir = tmp_path / "g4_output_package"
    project_dir.mkdir()
    output_dir.mkdir()
    (output_dir / "g4_summary.json").write_text(
        json.dumps({"job_id": "quality", "events_requested": 10, "smoke_success": True}),
        encoding="utf-8",
    )
    (output_dir / "event_table.csv").write_text("EventID,edep_MeV,dose_Gy\n", encoding="utf-8")
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,0\n1,0,0,0\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0\n1,0,0,0\n",
        encoding="utf-8",
    )
    (output_dir / "provenance.json").write_text('{"job_id":"quality"}\n', encoding="utf-8")
    (output_dir / "smoke_simulation_result.json").write_text(
        json.dumps(
            {
                "success": True,
                "errors": "parameter value (Phantom) is not listed in the candidate List.",
            }
        ),
        encoding="utf-8",
    )
    for name in (
        "cmake_configure_result.json",
        "build_result.json",
        "unit_test_result.json",
    ):
        (output_dir / name).write_text('{"success": true}', encoding="utf-8")

    gate = gia._summarize_runtime_gate_result(
        result={"success": True, "warnings": []},
        attempt=1,
        project_dir=project_dir,
        output_dir=output_dir,
    )

    assert gate["status"] == "fail"
    assert any("event_table.csv has no event rows" in error for error in gate["errors"])
    assert any("edep_3d.csv has no non-zero edep_MeV bins" in error for error in gate["errors"])
    assert any("dose_3d.csv has no non-zero dose_Gy bins" in error for error in gate["errors"])
    assert any("Smoke simulation stderr" in error for error in gate["errors"])


def test_runtime_failure_context_includes_smoke_log_and_runtime_sources(tmp_path) -> None:
    project_dir = tmp_path / "runtime_attempt_1" / "geant4_project"
    output_dir = tmp_path / "runtime_attempt_1" / "g4_output_package"
    (project_dir / "src").mkdir(parents=True)
    output_dir.mkdir(parents=True)
    (project_dir / "main.cc").write_text("int main() { return 0; }\n", encoding="utf-8")
    (project_dir / "src" / "ScoringManager.cc").write_text(
        "void CollectEventData() { /* scoring observation */ }\n",
        encoding="utf-8",
    )
    smoke_path = output_dir / "smoke_simulation_result.json"
    smoke_path.write_text(
        json.dumps(
            {
                "success": False,
                "log_tail": "SMOKE_LOG_SENTINEL: entered run initialization",
                "errors": "Segmentation fault (core dumped)",
            }
        ),
        encoding="utf-8",
    )

    compact = gia._compact_runtime_failure_context(
        {
            "status": "fail",
            "project_dir": str(project_dir),
            "artifacts": [str(smoke_path)],
            "errors": ["runtime failed"],
        }
    )

    artifact_text = json.dumps(compact["artifact_summaries"], ensure_ascii=False)
    source_text = json.dumps(compact["runtime_project_files"], ensure_ascii=False)
    assert "SMOKE_LOG_SENTINEL" in artifact_text
    assert "src/ScoringManager.cc" in source_text
    assert "scoring observation" in source_text


@pytest.mark.asyncio
async def test_global_integration_agent_mock_provider_keeps_patch_and_requires_runtime_gate(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _Gateway({}, mock=True),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_mock",
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert report["status"] == "passed"
    assert report["mock_provider_only"] is True
    assert repaired["metadata"]["global_integration_agent"]["runtime_gate_required"] is True


@pytest.mark.asyncio
async def test_global_integration_agent_reacts_to_runtime_gate_observation(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    responses = [
        {
            "status": "integrated",
            "proposed_patch": {
                "changed_files": [
                    {"path": "main.cc", "new_content": "int main() { return 1; }\n"}
                ]
            },
            "issues_fixed": [{"target": "main.cc", "message": "initial integration"}],
            "errors": [],
        },
        {
            "status": "integrated",
            "proposed_patch": {
                "changed_files": [
                    {"path": "main.cc", "new_content": "int main() { return 0; }\n"}
                ]
            },
            "issues_fixed": [{"target": "main.cc", "message": "fixed runtime failure"}],
            "errors": [],
        },
    ]
    gateway = _SequenceGateway(responses)
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        if attempt == 1:
            return {
                "status": "fail",
                "attempt": attempt,
                "errors": ["compile failed: main.cc returned wrong wiring"],
                "warnings": [],
                "missing_outputs": ["g4_summary.json"],
            }
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_react",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_repair_rounds=2,
    )

    assert report["status"] == "passed"
    assert runtime_attempts == [1, 2]
    assert len(gateway.prompts) == 2
    assert "runtime repair round 1" in gateway.prompts[1]
    assert "compile failed: main.cc returned wrong wiring" in gateway.prompts[1]
    main_entry = next(f for f in repaired["changed_files"] if f["path"] == "main.cc")
    assert "return 0" in main_entry["new_content"]


@pytest.mark.asyncio
async def test_global_integration_runtime_repair_uses_large_context_and_token_budget(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    large_patch = {
        "changed_files": [
            {
                "path": "src/Large.cc",
                "operation": "create_or_replace",
                "new_content": "void f() {\n" + ("  // keep repair context visible\n" * 3_000),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
                "rationale": "test",
            },
            {
                "path": "main.cc",
                "operation": "create_or_replace",
                "new_content": "int main() { return 0; }\n",
                "zone": "runtime_app",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
                "rationale": "test",
            },
        ]
    }
    gateway = _Gateway(
        {
            "status": "integrated",
            "proposed_patch": {
                "changed_files": [
                    {"path": "main.cc", "new_content": "int main() { return 0; }\n"}
                ]
            },
            "issues_fixed": [],
            "errors": [],
        }
    )

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    _repaired, report = await run_global_integration_agent(
        large_patch,
        job_id="global_integration_large_repair_context",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_failure_context={"status": "fail", "errors": ["real build failed"]},
    )

    assert report["status"] == "passed"
    assert gateway.call_kwargs[0]["max_tokens"] >= 65_536
    assert len(gateway.prompts[0]) > 80_000


@pytest.mark.asyncio
async def test_global_integration_runtime_attempt_offset_resumes_after_existing_attempt(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    response = {
        "status": "integrated",
        "proposed_patch": {
            "changed_files": [
                {"path": "main.cc", "new_content": "int main() { return 0; }\n"}
            ]
        },
        "issues_fixed": [{"target": "main.cc", "message": "resume from attempt 1"}],
        "errors": [],
    }
    gateway = _Gateway(response)
    runtime_attempts: list[int] = []

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        attempt = int(kwargs["attempt"])
        runtime_attempts.append(attempt)
        return {
            "status": "pass",
            "attempt": attempt,
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
        }

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_resume_offset",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_failure_context={"status": "fail", "errors": ["attempt 1 failed"]},
        runtime_repair_rounds=1,
        runtime_attempt_offset=1,
    )

    assert report["status"] == "passed"
    assert runtime_attempts == [2]
    assert "runtime repair round 1" in gateway.prompts[0]
    assert "attempt 1 failed" in gateway.prompts[0]


@pytest.mark.asyncio
async def test_global_integration_persists_repairing_state_before_retry_call(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    gateway = _InitialThenErrorGateway(
        {
            "status": "integrated",
            "proposed_patch": {
                "changed_files": [
                    {"path": "main.cc", "new_content": "int main() { return 1; }\n"}
                ]
            },
            "issues_fixed": [{"target": "main.cc", "message": "initial integration"}],
            "errors": [],
        },
        error="network interrupted",
    )
    persisted_statuses: list[tuple[str, int]] = []
    original_persist_report = gia._persist_report

    def capture_report(report: dict[str, Any], job_id: str) -> None:
        persisted_statuses.append(
            (str(report.get("status")), len(report.get("runtime_gate_attempts", [])))
        )
        original_persist_report(report, job_id)

    async def runtime_gate(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": "fail",
            "attempt": int(kwargs["attempt"]),
            "errors": ["compile failed after initial patch"],
            "warnings": [],
            "missing_outputs": ["g4_summary.json"],
        }

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: gateway,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _database_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._run_integration_runtime_gate",
        runtime_gate,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._persist_report",
        capture_report,
    )

    _repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_incremental_persist",
        module_results={"simulation_core": {}, "runtime_app": {}},
        runtime_repair_rounds=2,
    )

    assert report["status"] == "failed"
    assert ("repairing", 1) in persisted_statuses
    assert report["runtime_gate_attempts"][0]["errors"] == ["compile failed after initial patch"]
    persisted_patch = json.loads(
        (
            tmp_path
            / "jobs"
            / "global_integration_incremental_persist"
            / STAGE_CODEGEN
            / "proposed_patch.json"
        ).read_text(encoding="utf-8")
    )
    main_entry = next(f for f in persisted_patch["changed_files"] if f["path"] == "main.cc")
    assert "return 1" in main_entry["new_content"]


@pytest.mark.asyncio
async def test_global_integration_node_uses_five_runtime_react_rounds(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_run_global_integration_agent(proposed_patch: dict[str, Any], **kwargs: Any):
        captured.update(kwargs)
        return proposed_patch, {"status": "passed", "errors": [], "issues_fixed": []}

    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.run_global_integration_agent",
        fake_run_global_integration_agent,
    )

    result = await global_integration_agent_node(
        {
            "job_id": "node_rounds",
            "proposed_patch": _patch(),
            "module_results": {},
            "module_contracts": {},
            "module_contexts": {},
            "interface_contracts": {},
            "runtime_failure_context": {},
            "codegen_errors": [],
        }
    )

    assert captured["runtime_repair_rounds"] == GLOBAL_INTEGRATION_RUNTIME_REPAIR_ROUNDS
    assert result["global_integration_agent_report"]["status"] == "passed"
