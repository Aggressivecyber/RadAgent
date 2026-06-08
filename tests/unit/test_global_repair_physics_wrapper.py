"""Global repair fixes physics wrapper integration patterns."""

from __future__ import annotations

from agent_core.g4_codegen.global_repair import run_global_code_repair


def test_global_repair_uses_create_physics_list(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "main.cc",
                "new_content": (
                    '#include "PhysicsListFactoryWrapper.hh"\n'
                    "int main() {\n"
                    "    auto* runManager = GetRunManager();\n"
                    "    runManager->SetUserInitialization(new PhysicsListFactoryWrapper());\n"
                    "}\n"
                ),
                "module_name": "main_cmake",
                "generated_by": "main_cmake_module_agent",
            },
            {
                "path": "include/PhysicsListFactoryWrapper.hh",
                "new_content": (
                    "#pragma once\n"
                    "class G4VModularPhysicsList;\n"
                    "class PhysicsListFactoryWrapper {\n"
                    "public:\n"
                    "  G4VUserPhysicsList* CreatePhysicsList();\n"
                    "  static G4VModularPhysicsList* list();\n"
                    "};\n"
                ),
                "module_name": "physics",
                "generated_by": "physics_module_agent",
            },
            {
                "path": "src/PhysicsListFactoryWrapper.cc",
                "new_content": (
                    '#include "PhysicsListFactoryWrapper.hh"\n'
                    "G4VModularPhysicsList* PhysicsListFactoryWrapper::list() {\n"
                    "    return CreatePhysicsList();\n"
                    "}\n"
                ),
                "module_name": "physics",
                "generated_by": "physics_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    by_path = {file["path"]: file["new_content"] for file in repaired["changed_files"]}

    assert "SetUserInitialization(new PhysicsListFactoryWrapper())" not in by_path["main.cc"]
    assert "CreatePhysicsList()" in by_path["main.cc"]
    assert "static G4VModularPhysicsList* list();" not in by_path[
        "include/PhysicsListFactoryWrapper.hh"
    ]
    assert "PhysicsListFactoryWrapper::list" not in by_path["src/PhysicsListFactoryWrapper.cc"]
    assert report["issues_fixed"]


def test_global_repair_placement_adapter_uses_static_manager(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "include/PlacementManager.hh",
                "new_content": (
                    "#pragma once\n"
                    "class PlacementManager {\n"
                    "public:\n"
                    "  G4PVPlacement* PlaceVolume(G4RotationMatrix*, const G4ThreeVector&, "
                    "G4LogicalVolume*, const G4String&, G4LogicalVolume*, G4bool, G4int, "
                    "G4bool);\n"
                    "};\n"
                ),
                "module_name": "placement",
                "generated_by": "placement_module_agent",
            },
            {
                "path": "src/PlacementManager.cc",
                "new_content": (
                    '#include "PlacementManager.hh"\n'
                    "G4PVPlacement* PlacementManager::Place(\n"
                    "    G4LogicalVolume* logical,\n"
                    "    const G4ThreeVector& position,\n"
                    "    G4RotationMatrix* rotation,\n"
                    "    G4LogicalVolume* mother,\n"
                    "    G4bool checkOverlaps) {\n"
                    "    return Instance()->PlaceVolume(\n"
                    "        logical, logical->GetName(), mother, position, rotation, 0,\n"
                    "        checkOverlaps);\n"
                    "}\n"
                ),
                "module_name": "placement",
                "generated_by": "placement_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    source = {
        file["path"]: file["new_content"] for file in repaired["changed_files"]
    }["src/PlacementManager.cc"]
    header = {
        file["path"]: file["new_content"] for file in repaired["changed_files"]
    }["include/PlacementManager.hh"]

    assert "static PlacementManager manager;" in source
    assert "manager.PlaceVolume(" in source
    assert "Instance()" not in source
    assert "static G4VPhysicalVolume* Place(" in header
    assert report["issues_fixed"]


def test_global_repair_normalizes_two_argument_default_cut(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "include/PhysicsListFactoryWrapper.hh",
                "new_content": (
                    "#pragma once\n"
                    "class PhysicsListFactoryWrapper {\n"
                    "public:\n"
                    "  G4VUserPhysicsList* CreatePhysicsList();\n"
                    "};\n"
                ),
                "module_name": "physics",
                "generated_by": "physics_module_agent",
            },
            {
                "path": "src/PhysicsListFactoryWrapper.cc",
                "new_content": (
                    '#include "PhysicsListFactoryWrapper.hh"\n'
                    "G4VUserPhysicsList* PhysicsListFactoryWrapper::CreatePhysicsList() {\n"
                    "  fPhysicsList->SetDefaultCutValue(0.7*mm, \"gamma\");\n"
                    "  return fPhysicsList;\n"
                    "}\n"
                ),
                "module_name": "physics",
                "generated_by": "physics_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    source = {
        file["path"]: file["new_content"] for file in repaired["changed_files"]
    }["src/PhysicsListFactoryWrapper.cc"]

    assert 'SetDefaultCutValue(0.7*mm, "gamma")' not in source
    assert "SetDefaultCutValue(0.7*mm);" in source
    assert any(
        issue["message"] == "normalized SetDefaultCutValue usage"
        for issue in report["issues_fixed"]
    )


def test_global_repair_scoring_and_sensitive_compile_patterns(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "src/ScoringManager.cc",
                "new_content": (
                    "void ScoringManager::RecordScoring() {\n"
                    "  auto* scMgr = G4ScoringManager::GetScoringManager();\n"
                    "  G4String meshName = scMgr->GetMeshName(iMesh);\n"
                    "  auto* mesh = scMgr->GetMesh(fMeshName);\n"
                    "}\n"
                ),
                "module_name": "scoring",
                "generated_by": "scoring_module_agent",
            },
            {
                "path": "include/SensitiveDetector.hh",
                "new_content": (
                    "#pragma once\n"
                    '#include "G4THitsCollection.hh"\n'
                    '#include "Hit.hh"\n'
                    "class SensitiveDetector {\n"
                    "  G4THitsCollection<Hit>* fHitsCollection;\n"
                    "};\n"
                ),
                "module_name": "sensitive_detector",
                "generated_by": "sensitive_detector_module_agent",
            },
            {
                "path": "src/SensitiveDetector.cc",
                "new_content": (
                    "void SensitiveDetector::Initialize(G4HCofThisEvent*) {\n"
                    "  fHitsCollection = new G4THitsCollection<Hit>(GetName(), "
                    "collectionName[0]);\n"
                    "}\n"
                    "G4bool SensitiveDetector::ProcessHits(G4Step*, G4TouchableHistory*) {\n"
                    "  Hit* hit = new Hit();\n"
                    "  return true;\n"
                    "}\n"
                ),
                "module_name": "sensitive_detector",
                "generated_by": "sensitive_detector_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    by_path = {file["path"]: file["new_content"] for file in repaired["changed_files"]}

    assert "GetMeshName" not in by_path["src/ScoringManager.cc"]
    assert "GetMesh(fMeshName)" not in by_path["src/ScoringManager.cc"]
    assert '"scoringMesh"' in by_path["src/ScoringManager.cc"]
    assert "GetMesh(0)" in by_path["src/ScoringManager.cc"]
    assert "G4THitsCollection<::Hit>* fHitsCollection" in by_path[
        "include/SensitiveDetector.hh"
    ]
    assert "new G4THitsCollection<::Hit>" in by_path["src/SensitiveDetector.cc"]
    assert "::Hit* hit = new ::Hit();" in by_path["src/SensitiveDetector.cc"]
    assert report["issues_fixed"]
