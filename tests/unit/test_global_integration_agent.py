from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agent_core.g4_codegen import global_integration_agent as gia
from agent_core.g4_codegen.global_integration_agent import run_global_integration_agent
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


def test_persist_report_appends_attempt_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    job_id = "global_report_history"

    first = {
        "job_id": job_id,
        "status": "failed",
        "errors": ["first failed"],
        "runtime_gate_attempts": [{"attempt": 1, "status": "fail"}],
        "agentic": {"stop_reason": "max_turns", "n_turns": 48},
        "continuation_request": {"status": "pending"},
    }
    second = {
        "job_id": job_id,
        "status": "failed",
        "errors": ["second failed"],
        "runtime_gate_attempts": [{"attempt": 2, "status": "fail"}],
        "agentic": {"stop_reason": "stalled_repeated_tool_result", "n_turns": 11},
    }

    gia._persist_report(first, job_id)
    gia._persist_report(second, job_id)

    codegen_dir = tmp_path / "jobs" / job_id / STAGE_CODEGEN
    latest = json.loads((codegen_dir / "global_integration_agent_report.json").read_text())
    history_path = codegen_dir / "integration" / "global_integration_attempts.jsonl"
    history = [json.loads(line) for line in history_path.read_text().splitlines()]

    assert latest["errors"] == ["second failed"]
    assert len(history) == 2
    assert history[0]["errors"] == ["first failed"]
    assert history[0]["agentic"]["stop_reason"] == "max_turns"
    assert history[0]["continuation_request"]["status"] == "pending"
    assert history[1]["runtime_gate_attempts"][0]["attempt"] == 2
    assert history[1]["agentic"]["n_turns"] == 11


def _write_visual_artifacts(output_dir: Path) -> None:
    (output_dir / "geometry_view.json").write_text(
        json.dumps(
            {
                "components": [
                    {
                        "id": "detector",
                        "name": "Detector",
                        "shape": "box",
                        "material": "G4_Si",
                        "size_mm": [1.0, 1.0, 1.0],
                        "position_mm": [0.0, 0.0, 0.0],
                        "rotation_deg": [0.0, 0.0, 0.0],
                        "opacity": 0.7,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "particle_tracks.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "event_id": 0,
                        "track_id": 1,
                        "particle": "proton",
                        "energy_MeV": 10.0,
                        "points_mm": [[0.0, 0.0, -1.0], [0.0, 0.0, 0.0]],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "energy_deposits.json").write_text(
        json.dumps(
            {
                "deposits": [
                    {
                        "event_id": 0,
                        "track_id": 1,
                        "volume": "detector",
                        "position_mm": [0.0, 0.0, 0.0],
                        "edep_MeV": 1.0,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


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


def test_global_integration_rejects_candidate_paths_outside_auto_apply_policy() -> None:
    candidate = {
        "changed_files": [
            {
                "path": "build.sh",
                "new_content": "#!/usr/bin/env bash\ncmake .\n",
                "zone": "green",
                "generated_by": "global_integration_agent",
                "module_name": "runtime_app",
            },
            {
                "path": "CMakePresets.json",
                "new_content": "{}\n",
                "zone": "green",
                "generated_by": "global_integration_agent",
                "module_name": "runtime_app",
            },
        ]
    }

    errors = gia._validate_candidate_patch_schema(_patch(), candidate)

    assert any("build.sh" in error and "not allowed" in error for error in errors)
    assert any("CMakePresets.json" in error and "not allowed" in error for error in errors)


def test_runtime_failure_context_includes_compile_error_source_snippets(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "geant4_project"
    source_path = project_dir / "src" / "SensitiveDetector.cc"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        "\n".join(
            [
                '#include "SensitiveDetector.hh"',
                "void SensitiveDetector::EndOfEvent(G4HCofThisEvent*)",
                "{",
                "  Hit* hitPtr = nullptr;",
                "  hitPtr->Print();",
                "}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compiler_error = (
        f"{source_path}:4:8: error: 'hitPtr' was not declared in this scope\n"
        "    4 |   Hit* hitPtr = nullptr;\n"
        "      |        ^~~~~~\n"
    )

    compact = gia._compact_runtime_failure_context(
        {
            "status": "fail",
            "project_dir": str(project_dir),
            "errors": [compiler_error],
            "build_result": {"errors": compiler_error},
            "output_summary": {"large_payload": "x" * 50_000},
        }
    )

    snippets = compact["compile_error_contexts"]
    assert snippets[0]["path"] == "src/SensitiveDetector.cc"
    assert snippets[0]["line"] == 4
    assert "hitPtr" in snippets[0]["diagnostic"]
    assert "  Hit* hitPtr = nullptr;" in snippets[0]["source_excerpt"]
    assert "void SensitiveDetector::EndOfEvent" in snippets[0]["source_excerpt"]


def test_runtime_failure_context_reads_compile_errors_from_artifacts(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "geant4_project"
    source_path = project_dir / "src" / "SensitiveDetector.cc"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        '#include "SensitiveDetector.hh"\n'
        "void SensitiveDetector::EndOfEvent(G4HCofThisEvent*)\n"
        "{\n"
        "  Hit* hitPtr = nullptr;\n"
        "}\n",
        encoding="utf-8",
    )
    runtime_gate = tmp_path / "runtime_gate_result.json"
    runtime_gate.write_text(
        json.dumps(
            {
                "status": "fail",
                "errors": [
                    f"{source_path}:4:8: error: 'hitPtr' was not declared in this scope"
                ],
            }
        ),
        encoding="utf-8",
    )

    compact = gia._compact_runtime_failure_context(
        {
            "status": "fail",
            "project_dir": str(project_dir),
            "artifacts": [{"path": str(runtime_gate)}],
        }
    )

    snippets = compact["compile_error_contexts"]
    assert snippets[0]["path"] == "src/SensitiveDetector.cc"
    assert snippets[0]["line"] == 4
    assert "Hit* hitPtr" in snippets[0]["source_excerpt"]


def test_compile_error_context_includes_related_local_project_files(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "geant4_project"
    source_path = project_dir / "src" / "Consumer.cc"
    header_path = project_dir / "include" / "Widget.hh"
    companion_header = project_dir / "include" / "Consumer.hh"
    companion_source = project_dir / "src" / "Widget.cc"
    source_path.parent.mkdir(parents=True)
    header_path.parent.mkdir(parents=True)
    source_path.write_text(
        '#include "Consumer.hh"\n'
        '#include "Widget.hh"\n'
        "void Consumer::UseWidget()\n"
        "{\n"
        "  MissingWidgetType value;\n"
        "}\n",
        encoding="utf-8",
    )
    header_path.write_text(
        "#pragma once\nclass Widget { public: void Touch(); };\n",
        encoding="utf-8",
    )
    companion_header.write_text(
        "#pragma once\nclass Consumer { public: void UseWidget(); };\n",
        encoding="utf-8",
    )
    companion_source.write_text(
        '#include "Widget.hh"\nvoid Widget::Touch() {}\n',
        encoding="utf-8",
    )
    compiler_error = (
        f"{source_path}:5:3: error: 'MissingWidgetType' was not declared in this scope\n"
        "    5 |   MissingWidgetType value;\n"
        "      |   ^~~~~~~~~~~~~~~~~\n"
    )

    compact = gia._compact_runtime_failure_context(
        {
            "status": "fail",
            "project_dir": str(project_dir),
            "errors": [compiler_error],
        }
    )

    related = compact["compile_error_contexts"][0]["related_files"]
    related_by_path = {item["path"]: item for item in related}
    assert "include/Consumer.hh" in related_by_path
    assert "include/Widget.hh" in related_by_path
    assert "src/Widget.cc" in related_by_path
    assert "class Widget" in related_by_path["include/Widget.hh"]["content_excerpt"]


def test_integration_query_includes_runtime_compile_error_text() -> None:
    query = gia._build_integration_query(
        {
            "project_files": [],
            "runtime_failure_context": {
                "errors": [
                    "/tmp/geant4_project/src/Consumer.cc:5:3: error: MissingWidgetType"
                ],
                "build_result": {
                    "errors": "src/Consumer.cc:5:3: error: MissingWidgetType"
                },
                "compile_error_contexts": [
                    {
                        "path": "src/Consumer.cc",
                        "message": "MissingWidgetType was not declared",
                    }
                ],
            },
        }
    )

    assert "MissingWidgetType" in query
    assert "src/Consumer.cc" in query


def test_model_context_includes_geant4_repair_memory_under_budget() -> None:
    text = gia._model_context_json(
        {
            "job_id": "job_memory",
            "available_modules": ["runtime_app"],
            "project_files": [
                {
                    "path": "src/OutputManager.cc",
                    "new_content": "x" * 80_000,
                    "module_name": "runtime_app",
                }
            ],
            "runtime_failure_context": {},
            "integration_memory": {},
            "write_contract": {},
        },
        max_chars=20_000,
        max_project_file_chars=15_000,
    )
    context = json.loads(text)
    memory_text = json.dumps(context.get("geant4_repair_memory", {}), ensure_ascii=False)

    assert "fGeometryComponents" in memory_text
    assert "geometry_view.json" in memory_text
    assert "particle_tracks.json" in memory_text
    assert "energy_deposits.json" in memory_text
    assert "event_table.csv" in memory_text
    assert "g4_summary.json" in memory_text


def test_model_context_includes_agentic_repair_lessons() -> None:
    text = gia._model_context_json(
        {
            "job_id": "job_memory",
            "available_modules": ["runtime_app"],
            "project_files": [],
            "runtime_failure_context": {},
            "integration_memory": {
                "agentic_repair_lessons": {
                    "lessons": [
                        {
                            "id": "geometry_view_phantom_member",
                            "prompt_instruction": "Check OutputManager.hh before using fGeometryComponents.",
                            "count": 2,
                        }
                    ]
                }
            },
            "write_contract": {},
        },
        max_chars=20_000,
        max_project_file_chars=15_000,
    )
    context = json.loads(text)
    lessons = context["integration_memory"]["agentic_repair_lessons"]["lessons"]

    assert lessons[0]["id"] == "geometry_view_phantom_member"
    assert "fGeometryComponents" in lessons[0]["prompt_instruction"]


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


def test_global_integration_normalizes_real_g4_ir_units_without_overriding_run_events() -> None:
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
    assert "/run/beamOn 10" in run_macro
    assert "/run/beamOn 1000" not in run_macro


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


def test_global_integration_postprocesses_runtime_output_manager_fallbacks() -> None:
    output_manager = (
        '#include "OutputManager.hh"\n'
        "#include <fstream>\n"
        "#include <iomanip>\n"
        "#include <map>\n"
        "void OutputManager::AddEnergyDeposit(G4int eventID, G4int trackID,\n"
        "                                      const G4String& volume,\n"
        "                                      G4double x, G4double y, G4double z,\n"
        "                                      G4double edepMeV)\n"
        "{\n"
        "  if (edepMeV <= 0.0) return;\n"
        "  std::lock_guard<std::mutex> lock(fMutex);\n"
        "  fDeposits.push_back({eventID, trackID, volume, x, y, z, edepMeV});\n"
        "}\n"
        "void OutputManager::WriteSummaryJson()\n"
        "{\n"
        "  G4double totalEdep = 0.0;\n"
        "  for (const auto& r : fEventRows) totalEdep += r.edepMeV;\n"
        "}\n"
        "void OutputManager::WriteEventTableCsv()\n"
        "{\n"
        "  for (const auto& r : fEventRows) { ofs << r.eventID << r.edepMeV << r.doseGy; }\n"
        "}\n"
        "void OutputManager::WriteEdep3dCsv()\n"
        "{\n"
        "  for (const auto& b : fVoxelBins) { ofs << b.x << b.y << b.z << b.edepMeV; }\n"
        "}\n"
        "void OutputManager::WriteDose3dCsv()\n"
        "{\n"
        "  for (const auto& b : fVoxelBins) { ofs << b.x << b.y << b.z << b.doseGy; }\n"
        "}\n"
    )
    original_patch = {
        "changed_files": [
            {
                "path": "src/OutputManager.cc",
                "operation": "create_or_replace",
                "new_content": output_manager,
                "zone": "green",
                "generated_by": "runtime_app_module_agent",
                "module_name": "runtime_app",
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, original_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert "_BuildEventRowsFromDeposits" in content
    assert "_BuildVoxelBinsFromDeposits" in content
    assert "for (const auto& r : eventRowsForOutput)" in content
    assert "for (const auto& b : voxelBinsForOutput)" in content


def test_global_integration_adds_vis_attributes_include_for_static_access() -> None:
    original_patch = {
        "changed_files": [
            {
                "path": "src/DetectorConstruction.cc",
                "operation": "create_or_replace",
                "new_content": (
                    '#include "DetectorConstruction.hh"\n'
                    "G4VPhysicalVolume* DetectorConstruction::Construct() {\n"
                    "  worldLV->SetVisAttributes(G4VisAttributes::GetInvisible());\n"
                    "  return worldPV;\n"
                    "}\n"
                ),
                "zone": "green",
                "generated_by": "simulation_core_module_agent",
                "module_name": "simulation_core",
            }
        ]
    }

    repaired, errors = gia._merge_patch_by_path(original_patch, original_patch)

    assert errors == []
    content = repaired["changed_files"][0]["new_content"]
    assert '#include "G4VisAttributes.hh"' in content
    assert content.index('#include "G4VisAttributes.hh"') < content.index(
        "G4VisAttributes::GetInvisible"
    )


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
async def test_global_integration_short_circuits_when_initial_runtime_gate_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: _FailIfCalledGateway(),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )
    gate_calls: list[int] = []

    async def fake_runtime_gate(**kwargs: Any) -> dict[str, Any]:
        gate_calls.append(int(kwargs["attempt"]))
        return {
            "status": "pass",
            "attempt": kwargs["attempt"],
            "errors": [],
            "warnings": [],
            "missing_outputs": [],
            "output_quality": {"status": "pass", "errors": []},
        }

    async def fail_repair(*_args: Any, **_kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        raise AssertionError("repair should not run after an initial runtime gate pass")

    monkeypatch.setattr(gia, "_run_integration_runtime_gate", fake_runtime_gate)
    monkeypatch.setattr(
        "agent_core.g4_codegen.agentic_repair.run_agentic_repair",
        fail_repair,
    )

    repaired, report = await run_global_integration_agent(
        _patch(),
        job_id="global_integration_gate_short_circuit",
        g4_model_ir={"sources": [{"events": 5}]},
        module_results={"simulation_core": {}, "runtime_app": {}},
    )

    assert gate_calls == [0]
    assert report["status"] == "passed"
    assert report["runtime_gate_attempts"][0]["status"] == "pass"
    assert report["changed_files"] == []
    assert "agentic" not in report
    assert repaired["metadata"]["global_integration_agent"]["runtime_gate_required"] is True


@pytest.mark.asyncio
async def test_integration_runtime_gate_uses_requested_ir_event_count(
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
            assert events == 5
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
            _write_visual_artifacts(out)
            return {
                "success": True,
                "cmake_configure_result": {"success": True},
                "build_result": {"success": True},
                "unit_test_result": {"success": True},
                "warnings": [],
            }

    monkeypatch.setattr("agent_core.tools.geant4_runner.Geant4Runner", FakeRunner)

    gate = await gia._run_integration_runtime_gate(
        job_id="runtime_gate_ir_events",
        proposed_patch=_patch(),
        attempt=1,
        expected_events=5,
    )

    assert seen["events"] == 5
    assert gate["status"] == "pass"
    assert gate["expected_events"] == 5


@pytest.mark.asyncio
async def test_integration_runtime_gate_records_runner_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

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
            return {
                "success": False,
                "cmake_configure_result": {
                    "success": False,
                    "command": "cmake bad-relative-source",
                    "errors": "configure failed",
                },
                "warnings": ["configure failed"],
            }

    monkeypatch.setattr("agent_core.tools.geant4_runner.Geant4Runner", FakeRunner)

    gate = await gia._run_integration_runtime_gate(
        job_id="runtime_gate_contract",
        proposed_patch=_patch(),
        attempt=1,
    )

    contract = gate["runner_contract"]
    assert contract["runner"] == "Geant4Runner.smoke_test"
    assert contract["events"] == 1000
    assert Path(contract["project_dir_abs"]).is_absolute()
    assert Path(contract["build_dir_abs"]).is_absolute()
    assert contract["configure_command_shape"].startswith("cmake ")
    assert "build.sh" in contract["forbidden_path_examples"]
    assert "src/*.cc" in contract["allowed_path_patterns"]


def test_global_integration_runtime_gate_rejects_event_count_mismatch(tmp_path) -> None:
    project_dir = tmp_path / "geant4_project"
    output_dir = tmp_path / "g4_output_package"
    project_dir.mkdir()
    output_dir.mkdir()
    (output_dir / "g4_summary.json").write_text(
        json.dumps({"job_id": "quality", "events_requested": 1000, "smoke_success": True}),
        encoding="utf-8",
    )
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n"
        + "\n".join(f"{i},1.0,0.01" for i in range(1000))
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text("x,y,z,edep_MeV\n0,0,0,1.0\n", encoding="utf-8")
    (output_dir / "dose_3d.csv").write_text("x,y,z,dose_Gy\n0,0,0,0.01\n", encoding="utf-8")
    (output_dir / "provenance.json").write_text('{"job_id":"quality"}\n', encoding="utf-8")
    (output_dir / "smoke_simulation_result.json").write_text(
        json.dumps({"success": True, "errors": ""}),
        encoding="utf-8",
    )

    gate = gia._summarize_runtime_gate_result(
        result={"success": True, "warnings": []},
        attempt=1,
        project_dir=project_dir,
        output_dir=output_dir,
        expected_events=5,
    )

    assert gate["status"] == "fail"
    assert any("expected 5" in error for error in gate["errors"])


def test_model_context_includes_interface_audit() -> None:
    context_json = gia._model_context_json(
        {
            "job_id": "job_interface_audit",
            "available_modules": ["simulation_core"],
            "runtime_failure_context": {},
            "project_files": [],
            "database_search": {},
            "web_search": {},
            "interface_contracts": {},
            "interface_audit": {
                "status": "fail",
                "issues": [
                    {
                        "kind": "unknown_method",
                        "class_name": "PlacementManager",
                        "method": "RegisterPhysicalVolume",
                    }
                ],
            },
            "module_contracts": {},
            "module_result_diagnostics": {},
            "module_context_summaries": {},
            "integration_memory": {},
            "write_contract": {},
        },
        max_chars=20_000,
    )

    assert "interface_audit" in context_json
    assert "RegisterPhysicalVolume" in context_json
    assert "PlacementManager" in context_json


@pytest.mark.asyncio
async def test_global_integration_passes_interface_audit_to_agentic_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent.get_model_gateway",
        lambda: object(),
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_database",
        _empty_evidence,
    )
    monkeypatch.setattr(
        "agent_core.g4_codegen.global_integration_agent._search_web",
        _empty_evidence,
    )

    async def fake_runtime_gate(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": "fail",
            "attempt": kwargs["attempt"],
            "errors": ["compile failed"],
            "warnings": [],
            "missing_outputs": [],
        }

    seen: dict[str, Any] = {}

    async def fake_repair(
        proposed_patch: dict[str, Any],
        *,
        runtime_failure_context: dict[str, Any],
        **_kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        seen["runtime_failure_context"] = runtime_failure_context
        return proposed_patch, {"status": "failed", "errors": ["still failed"], "runtime_gate": {}}

    monkeypatch.setattr(gia, "_run_integration_runtime_gate", fake_runtime_gate)
    monkeypatch.setattr(
        "agent_core.g4_codegen.agentic_repair.run_agentic_repair",
        fake_repair,
    )

    await run_global_integration_agent(
        {
            "metadata": {
                "interface_audit": {
                    "status": "fail",
                    "issues": [
                        {
                            "kind": "constructor_arity_mismatch",
                            "class_name": "SensitiveDetector",
                            "path": "src/DetectorConstruction.cc",
                            "line": 1,
                        }
                    ],
                    "repair_hints": [
                        "Align src/DetectorConstruction.cc with include/SensitiveDetector.hh: "
                        "new SensitiveDetector(...) passes 1 argument but the generated header "
                        "declares arity 2."
                    ],
                }
            },
            "changed_files": [
                {
                    "path": "include/SensitiveDetector.hh",
                    "new_content": (
                        "class ScoringManager;\n"
                        "class SensitiveDetector {\n"
                        " public:\n"
                        "  SensitiveDetector(const G4String& name, ScoringManager* scoring);\n"
                        "};\n"
                    ),
                    "module_name": "simulation_core",
                },
                {
                    "path": "src/DetectorConstruction.cc",
                    "new_content": 'void DetectorConstruction::ConstructSDandField(){ new SensitiveDetector("water"); }\n',
                    "module_name": "simulation_core",
                },
            ]
        },
        job_id="job_interface_audit_repair_context",
    )

    audit = seen["runtime_failure_context"]["interface_audit"]
    assert audit["status"] == "fail"
    assert audit["issues"][0]["kind"] == "constructor_arity_mismatch"
    assert "SensitiveDetector" in audit["repair_hints"][0]


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


def test_global_integration_runtime_gate_prioritizes_runtime_fatal_error(tmp_path) -> None:
    project_dir = tmp_path / "geant4_project"
    output_dir = tmp_path / "g4_output_package"
    project_dir.mkdir()
    output_dir.mkdir()
    fatal = (
        "*** G4Exception : GeomMgt0002\n"
        "Logical volume <WorldLV>\n"
        "does not have a valid material pointer.\n"
        "Aborted (core dumped)\n"
    )
    (output_dir / "smoke_simulation_result.json").write_text(
        json.dumps(
            {
                "success": False,
                "process_success": False,
                "runtime_error_patterns": ["FatalException", "core dumped"],
                "errors": fatal,
            }
        ),
        encoding="utf-8",
    )

    gate = gia._summarize_runtime_gate_result(
        result={
            "success": False,
            "warnings": [fatal],
            "run_errors": fatal,
            "runtime_error_patterns": ["FatalException", "core dumped"],
            "unit_test_result": {"success": False, "errors": "No tests were found!!!\n"},
        },
        attempt=1,
        project_dir=project_dir,
        output_dir=output_dir,
        expected_events=5,
    )

    assert gate["status"] == "fail"
    assert "GeomMgt0002" in gate["errors"][0]
    assert "WorldLV" in gate["errors"][0]
    assert any("Missing output contract files" in error for error in gate["errors"])


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
