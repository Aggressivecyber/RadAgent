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
                    "G4LogicalVolume*, const G4String&, G4VPhysicalVolume* mother, "
                    "G4bool, G4int, G4bool);\n"
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
                    "G4VPhysicalVolume* PlacementManager::PlaceVolume(\n"
                    "    G4RotationMatrix*, const G4ThreeVector&, G4LogicalVolume*, "
                    "const G4String&, G4VPhysicalVolume* mother, G4bool, G4int, G4bool) {\n"
                    "    return nullptr;\n"
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

    assert "static PlacementManager manager;" not in source
    assert "PlacementManager::PlaceVolume(" in source
    assert "Instance()" not in source
    assert "static G4VPhysicalVolume* Place(" in header
    assert '#include "G4RotationMatrix.hh"' in header
    assert "class G4RotationMatrix;" not in header
    assert "G4VPhysicalVolume* mother" not in header
    assert "G4VPhysicalVolume* mother" not in source
    assert "G4LogicalVolume* mother" in header
    assert report["issues_fixed"]


def test_global_repair_main_uses_detector_material_registry_constructor(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "main.cc",
                "new_content": (
                    '#include "DetectorConstruction.hh"\n'
                    "int main() {\n"
                    "    auto* runManager = G4RunManagerFactory::CreateRunManager();\n"
                    "    runManager->SetUserInitialization(new DetectorConstruction());\n"
                    "}\n"
                ),
                "module_name": "main_cmake",
                "generated_by": "main_cmake_module_agent",
            },
            {
                "path": "include/DetectorConstruction.hh",
                "new_content": (
                    "#pragma once\n"
                    "class MaterialRegistry;\n"
                    "class DetectorConstruction {\n"
                    "public:\n"
                    "  DetectorConstruction(MaterialRegistry* registry);\n"
                    "};\n"
                ),
                "module_name": "geometry",
                "generated_by": "geometry_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    main = {file["path"]: file["new_content"] for file in repaired["changed_files"]}[
        "main.cc"
    ]

    assert '#include "MaterialRegistry.hh"' in main
    assert "auto* materialRegistry = MaterialRegistry::GetInstance();" in main
    assert "materialRegistry->Initialize();" in main
    assert "new DetectorConstruction(materialRegistry)" in main
    assert report["issues_fixed"]


def test_global_repair_adds_material_registry_singleton(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "include/MaterialRegistry.hh",
                "new_content": (
                    "#pragma once\n"
                    "class MaterialRegistry {\n"
                    "public:\n"
                    "  void Initialize();\n"
                    "};\n"
                ),
                "module_name": "material",
                "generated_by": "material_module_agent",
            },
            {
                "path": "src/MaterialRegistry.cc",
                "new_content": (
                    '#include "MaterialRegistry.hh"\n'
                    "void MaterialRegistry::Initialize() {}\n"
                ),
                "module_name": "material",
                "generated_by": "material_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    by_path = {file["path"]: file["new_content"] for file in repaired["changed_files"]}

    assert "static MaterialRegistry* GetInstance();" in by_path["include/MaterialRegistry.hh"]
    assert "MaterialRegistry* MaterialRegistry::GetInstance()" in by_path[
        "src/MaterialRegistry.cc"
    ]
    assert "static MaterialRegistry registry;" in by_path["src/MaterialRegistry.cc"]
    assert "return &registry;" in by_path["src/MaterialRegistry.cc"]
    assert report["issues_fixed"]


def test_global_repair_normalizes_material_registry_pointer_calls(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "src/DetectorConstruction.cc",
                "new_content": (
                    '#include "MaterialRegistry.hh"\n'
                    "void build() { MaterialRegistry::GetInstance().GetMaterial(\"G4_AIR\"); }\n"
                ),
                "module_name": "geometry",
                "generated_by": "geometry_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    source = {file["path"]: file["new_content"] for file in repaired["changed_files"]}[
        "src/DetectorConstruction.cc"
    ]

    assert "MaterialRegistry::GetInstance()->GetMaterial" in source
    assert report["issues_fixed"]


def test_global_repair_normalizes_invalid_g4_exception_severity(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "src/MaterialRegistry.cc",
                "new_content": (
                    '#include "G4Exception.hh"\n'
                    "void fail() { G4Exception(\"m\", \"c\", "
                    'FatalErrorInArguments, "bad"); }\n'
                ),
                "module_name": "material",
                "generated_by": "material_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    source = {file["path"]: file["new_content"] for file in repaired["changed_files"]}[
        "src/MaterialRegistry.cc"
    ]

    assert "FatalException" in source
    assert "FatalErrorInArguments" not in source
    assert report["issues_fixed"]


def test_global_repair_main_uses_material_registry_singleton_for_detector(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "main.cc",
                "new_content": (
                    '#include "MaterialRegistry.hh"\n'
                    '#include "DetectorConstruction.hh"\n'
                    "int main() {\n"
                    "  auto* materialRegistry = new MaterialRegistry();\n"
                    "  materialRegistry->Initialize();\n"
                    "  auto* detector = new DetectorConstruction(materialRegistry);\n"
                    "}\n"
                ),
                "module_name": "main_cmake",
                "generated_by": "main_cmake_module_agent",
            },
            {
                "path": "include/DetectorConstruction.hh",
                "new_content": (
                    "#pragma once\n"
                    "class MaterialRegistry;\n"
                    "class DetectorConstruction {\n"
                    "public:\n"
                    "  DetectorConstruction(MaterialRegistry* registry);\n"
                    "};\n"
                ),
                "module_name": "geometry",
                "generated_by": "geometry_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    main = {file["path"]: file["new_content"] for file in repaired["changed_files"]}[
        "main.cc"
    ]

    assert "new MaterialRegistry()" not in main
    assert "auto* materialRegistry = MaterialRegistry::GetInstance();" in main
    assert "new DetectorConstruction(materialRegistry)" in main
    assert report["issues_fixed"]


def test_global_repair_adds_placement_place_declaration_before_include_guard(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "CMakeLists.txt",
                "new_content": (
                    "cmake_minimum_required(VERSION 3.16)\n"
                    "project(RadSim LANGUAGES CXX)\n"
                    "add_executable(radapp main.cc src/PlacementManager.cc)\n"
                ),
                "module_name": "main_cmake",
                "generated_by": "main_cmake_module_agent",
            },
            {
                "path": "include/PlacementManager.hh",
                "new_content": (
                    "#ifndef PLACEMENT_MANAGER_HH\n"
                    "#define PLACEMENT_MANAGER_HH\n"
                    "class G4LogicalVolume;\n"
                    "class G4RotationMatrix;\n"
                    "class G4VPhysicalVolume;\n"
                    "class G4ThreeVector;\n"
                    "class PlacementManager {\n"
                    "public:\n"
                    "  static G4VPhysicalVolume* Place(\n"
                    "      G4RotationMatrix* rotation, const G4ThreeVector& position,\n"
                    "      G4LogicalVolume* logical, const char* name,\n"
                    "      G4LogicalVolume* mother);\n"
                    "};\n"
                    "#endif\n"
                ),
                "module_name": "placement",
                "generated_by": "placement_module_agent",
            },
            {
                "path": "src/PlacementManager.cc",
                "new_content": (
                    '#include "PlacementManager.hh"\n'
                    "G4VPhysicalVolume* PlacementManager::Place(\n"
                    "    G4LogicalVolume* logical,\n"
                    "    const G4ThreeVector& position,\n"
                    "    G4RotationMatrix* rotation,\n"
                    "    G4LogicalVolume* mother,\n"
                    "    G4bool checkOverlaps) {\n"
                    "  return PlacementManager::PlaceVolume(\n"
                    "      rotation, position, logical, logical->GetName(), mother,\n"
                    "      false, 0, checkOverlaps);\n"
                    "}\n"
                ),
                "module_name": "placement",
                "generated_by": "placement_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    header = {file["path"]: file["new_content"] for file in repaired["changed_files"]}[
        "include/PlacementManager.hh"
    ]

    assert (
        "G4LogicalVolume* logical,\n"
        "                                  const G4ThreeVector& position"
    ) in header
    assert header.index("G4LogicalVolume* logical") < header.index("#endif")
    assert report["issues_fixed"]


def test_global_repair_main_uses_default_detector_constructor_when_required(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "main.cc",
                "new_content": (
                    '#include "MaterialRegistry.hh"\n'
                    '#include "DetectorConstruction.hh"\n'
                    "int main() {\n"
                    "  MaterialRegistry* matReg = MaterialRegistry::GetInstance();\n"
                    "  matReg->Initialize();\n"
                    "  auto* detector = new DetectorConstruction(matReg);\n"
                    "}\n"
                ),
                "module_name": "main_cmake",
                "generated_by": "main_cmake_module_agent",
            },
            {
                "path": "include/DetectorConstruction.hh",
                "new_content": (
                    "#pragma once\n"
                    "class DetectorConstruction {\n"
                    "public:\n"
                    "  DetectorConstruction();\n"
                    "};\n"
                ),
                "module_name": "geometry",
                "generated_by": "geometry_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    main = {file["path"]: file["new_content"] for file in repaired["changed_files"]}[
        "main.cc"
    ]

    assert "matReg->Initialize()" not in main
    assert "new DetectorConstruction()" in main
    assert "new DetectorConstruction(matReg)" not in main
    assert report["issues_fixed"]


def test_global_repair_replaces_g4bestunit_include(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "src/Hit.cc",
                "new_content": '#include "Hit.hh"\n#include "G4BestUnit.hh"\n',
                "module_name": "sensitive_detector",
                "generated_by": "sensitive_detector_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    hit_source = {file["path"]: file["new_content"] for file in repaired["changed_files"]}[
        "src/Hit.cc"
    ]

    assert '#include "G4UnitsTable.hh"' in hit_source
    assert "G4BestUnit.hh" not in hit_source
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


def test_global_repair_removes_output_manager_action_casts(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    patch = {
        "changed_files": [
            {
                "path": "main.cc",
                "new_content": (
                    '#include "OutputManager.hh"\n'
                    "int main() {\n"
                    "  auto* outputMgr = OutputManager::Instance();\n"
                    "  runManager->SetUserAction(static_cast<G4UserRunAction*>(outputMgr));\n"
                    "  runManager->SetUserAction(static_cast<G4UserEventAction*>(outputMgr));\n"
                    "  runManager->SetUserAction(static_cast<G4UserSteppingAction*>(outputMgr));\n"
                    "}\n"
                ),
                "module_name": "main_cmake",
                "generated_by": "main_cmake_module_agent",
            },
        ]
    }

    repaired, report = run_global_code_repair(patch, "job")
    main = {file["path"]: file["new_content"] for file in repaired["changed_files"]}["main.cc"]

    assert "static_cast<G4UserRunAction*>" not in main
    assert "static_cast<G4UserEventAction*>" not in main
    assert "static_cast<G4UserSteppingAction*>" not in main
    assert any(
        issue["message"] == "removed invalid OutputManager user action casts"
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
                    "  auto& scoreMap = mesh->GetScoreMap();\n"
                    "  G4ThreeVector center;\n"
                    "  mesh->GetElementCenter(copyNo, center);\n"
                    "}\n"
                ),
                "module_name": "scoring",
                "generated_by": "scoring_module_agent",
            },
            {
                "path": "include/Hit.hh",
                "new_content": (
                    "#pragma once\n"
                    "class Hit {\n"
                    "public:\n"
                    "  inline void* operator new(size_t);\n"
                    "  inline void operator delete(void*);\n"
                    "};\n"
                ),
                "module_name": "sensitive_detector",
                "generated_by": "sensitive_detector_module_agent",
            },
            {
                "path": "src/Hit.cc",
                "new_content": (
                    '#include "Hit.hh"\n'
                    "G4Allocator<Hit> fAllocator;\n"
                    "void* Hit::operator new(size_t size) {\n"
                    "  return fAllocator.alloc(size);\n"
                    "}\n"
                    "void Hit::operator delete(void* hit) {\n"
                    "  fAllocator.free((Hit*)hit);\n"
                    "}\n"
                ),
                "module_name": "sensitive_detector",
                "generated_by": "sensitive_detector_module_agent",
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
                    "  fHitsCollection->push_back(hit);\n"
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
    assert "GetElementCenter" not in by_path["src/ScoringManager.cc"]
    assert '"scoringMesh"' in by_path["src/ScoringManager.cc"]
    assert "GetMesh(0)" in by_path["src/ScoringManager.cc"]
    assert "auto scoreMap = mesh->GetScoreMap();" in by_path["src/ScoringManager.cc"]
    assert "const int nxRaw" in by_path["src/ScoringManager.cc"]
    assert "G4THitsCollection<::Hit>* fHitsCollection" in by_path[
        "include/SensitiveDetector.hh"
    ]
    assert "new G4THitsCollection<::Hit>" in by_path["src/SensitiveDetector.cc"]
    assert "::Hit* hit = new ::Hit();" in by_path["src/SensitiveDetector.cc"]
    assert "fHitsCollection->insert(hit);" in by_path["src/SensitiveDetector.cc"]
    assert "inline void* operator new" not in by_path["include/Hit.hh"]
    assert "inline void operator delete" not in by_path["include/Hit.hh"]
    assert "fAllocator.MallocSingle()" in by_path["src/Hit.cc"]
    assert "fAllocator.FreeSingle(static_cast<Hit*>(hit))" in by_path["src/Hit.cc"]
    assert ".alloc(" not in by_path["src/Hit.cc"]
    assert ".free(" not in by_path["src/Hit.cc"]
    assert report["issues_fixed"]
