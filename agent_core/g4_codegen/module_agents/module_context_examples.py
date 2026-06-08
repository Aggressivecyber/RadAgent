"""Module-owned code examples and interface context for G4 codegen agents."""

from __future__ import annotations

from typing import Any

MODULE_LAYER_ORDER = [
    "material",
    "geometry",
    "placement",
    "source",
    "physics",
    "sensitive_detector",
    "scoring",
    "output_manager",
    "action_initialization",
    "main_cmake",
]


MODULE_CODE_EXAMPLES: dict[str, dict[str, Any]] = {
    "material": {
        "owned_files": ["include/MaterialRegistry.hh", "src/MaterialRegistry.cc"],
        "primary_symbols": ["MaterialRegistry"],
        "example": (
            "#pragma once\n"
            '#include "G4Material.hh"\n'
            '#include "G4String.hh"\n'
            "class MaterialRegistry {\n"
            "public:\n"
            "  void Initialize();\n"
            "  G4Material* GetMaterial(const G4String& name);\n"
            "  void AddCustomMaterial(const G4String& name, G4Material* material);\n"
            "};\n"
        ),
        "notes": [
            "Use one GetMaterial string overload to avoid literal ambiguity.",
            "Initialize must register real NIST/custom materials, not placeholders.",
        ],
    },
    "geometry": {
        "owned_files": ["include/DetectorConstruction.hh", "src/DetectorConstruction.cc"],
        "primary_symbols": ["DetectorConstruction"],
        "example": (
            "class DetectorConstruction : public G4VUserDetectorConstruction {\n"
            "public:\n"
            "  G4VPhysicalVolume* Construct() override;\n"
            "private:\n"
            "  MaterialRegistry* fMaterials;\n"
            "  PlacementManager* fPlacement;\n"
            "};\n"
        ),
        "notes": [
            "Construct the world volume here.",
            "Use MaterialRegistry for materials and PlacementManager for non-world placements.",
        ],
    },
    "placement": {
        "owned_files": ["include/PlacementManager.hh", "src/PlacementManager.cc"],
        "primary_symbols": ["PlacementManager"],
        "example": (
            "class PlacementManager {\n"
            "public:\n"
            "  G4VPhysicalVolume* PlaceVolume(G4RotationMatrix* rotation,\n"
            "      const G4ThreeVector& position, G4LogicalVolume* logical,\n"
            "      const G4String& name, G4LogicalVolume* mother,\n"
            "      G4bool many, G4int copyNo, G4bool checkOverlaps);\n"
            "  static G4VPhysicalVolume* Place(G4LogicalVolume* logical,\n"
            "      const G4ThreeVector& position, G4RotationMatrix* rotation,\n"
            "      G4LogicalVolume* mother, G4bool checkOverlaps = true);\n"
            "};\n"
        ),
        "notes": [
            "Pass a non-const G4RotationMatrix* to G4PVPlacement.",
            "Include G4RotationMatrix.hh instead of forward declaring G4RotationMatrix.",
            "Return G4VPhysicalVolume* from placement helper interfaces.",
            "Static Place helpers should directly call static PlaceVolume helpers.",
            "Use G4LogicalVolume* for mother logical volume parameters.",
            "Keep overlap checks enabled unless the IR explicitly says otherwise.",
        ],
    },
    "source": {
        "owned_files": ["include/PrimaryGeneratorAction.hh", "src/PrimaryGeneratorAction.cc"],
        "primary_symbols": ["PrimaryGeneratorAction"],
        "example": (
            "class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {\n"
            "public:\n"
            "  void GeneratePrimaries(G4Event* event) override;\n"
            "private:\n"
            "  std::unique_ptr<G4ParticleGun> fParticleGun;\n"
            "};\n"
        ),
        "notes": [
            "Set particle, energy, position, and momentum direction from source IR.",
            "Do not create geometry or physics objects in this module.",
        ],
    },
    "physics": {
        "owned_files": [
            "include/PhysicsListFactoryWrapper.hh",
            "src/PhysicsListFactoryWrapper.cc",
            "macros/physics_list.mac",
        ],
        "primary_symbols": ["PhysicsListFactoryWrapper"],
        "example": (
            "class PhysicsListFactoryWrapper {\n"
            "public:\n"
            "  PhysicsListFactoryWrapper();\n"
            "  ~PhysicsListFactoryWrapper() = default;\n"
            "  G4VUserPhysicsList* CreatePhysicsList();\n"
            "private:\n"
            "  G4PhysListFactory fFactory;\n"
            "  G4VUserPhysicsList* fPhysicsList = nullptr;\n"
            "};\n"
        ),
        "notes": [
            "GetReferencePhysList returns a list handed to Geant4 run manager ownership.",
            "Do not delete fPhysicsList.",
            "Use SetDefaultCutValue(value) with one argument; do not pass particle names.",
        ],
    },
    "sensitive_detector": {
        "owned_files": [
            "include/SensitiveDetector.hh",
            "src/SensitiveDetector.cc",
            "include/Hit.hh",
            "src/Hit.cc",
        ],
        "primary_symbols": ["SensitiveDetector", "Hit"],
        "example": (
            "class SensitiveDetector : public G4VSensitiveDetector {\n"
            "public:\n"
            "  G4bool ProcessHits(G4Step* step, G4TouchableHistory*) override;\n"
            "  void Initialize(G4HCofThisEvent* hce) override;\n"
            "};\n"
        ),
        "notes": [
            "Register collection names with collectionName.push_back(...).",
            "Use G4THitsCollection<::Hit> inside SensitiveDetector class scope.",
            "Add hits with fHitsCollection->insert(hit), not push_back(hit).",
            "Attach with logicalVolume->SetSensitiveDetector(this) when an attach helper exists.",
        ],
    },
    "scoring": {
        "owned_files": ["include/ScoringManager.hh", "src/ScoringManager.cc"],
        "primary_symbols": ["ScoringManager"],
        "example": (
            "class ScoringManager {\n"
            "public:\n"
            "  void ConfigureMesh();\n"
            "  void CollectScores();\n"
            "  const std::vector<ScoringRecord>& Records() const;\n"
            "};\n"
        ),
        "notes": [
            "Use G4VScoringMesh::GetScoreMap() for command-based mesh results.",
            "Store GetScoreMap() by value with auto scoreMap, not auto& scoreMap.",
            "Use G4ScoringManager::GetMesh(0) for the single configured mesh.",
            "Compute bin centers locally; do not call nonexistent GetElementCenter().",
            "Do not write output files; OutputManager owns persistence.",
        ],
    },
    "output_manager": {
        "owned_files": ["include/OutputManager.hh", "src/OutputManager.cc"],
        "primary_symbols": ["OutputManager"],
        "example": (
            "class OutputManager {\n"
            "public:\n"
            "  void BeginRun(const G4String& jobId);\n"
            "  void RecordScoringRow(const ScoringRecord& row);\n"
            "  void EndRun();\n"
            "};\n"
        ),
        "notes": [
            "Own CSV/JSON file writing and run metadata.",
            "Read scoring records through a stable ScoringManager-facing interface.",
        ],
    },
    "action_initialization": {
        "owned_files": [
            "include/ActionInitialization.hh",
            "src/ActionInitialization.cc",
            "include/RunAction.hh",
            "src/RunAction.cc",
        ],
        "primary_symbols": ["ActionInitialization", "RunAction"],
        "example": (
            "class ActionInitialization : public G4VUserActionInitialization {\n"
            "public:\n"
            "  void Build() const override;\n"
            "};\n"
        ),
        "notes": [
            "Register PrimaryGeneratorAction, RunAction, and other user actions.",
            "Do not instantiate DetectorConstruction or physics lists here.",
        ],
    },
    "main_cmake": {
        "owned_files": ["CMakeLists.txt", "main.cc", "macros/run.mac", "macros/init.mac"],
        "primary_symbols": ["main", "CMakeLists.txt"],
        "example": (
            "auto* runManager = new G4RunManager();\n"
            "runManager->SetUserInitialization(new DetectorConstruction());\n"
            "PhysicsListFactoryWrapper physics;\n"
            "runManager->SetUserInitialization(physics.CreatePhysicsList());\n"
            "runManager->SetUserInitialization(new ActionInitialization());\n"
        ),
        "notes": [
            "Use actual generated class names and constructors from upstream summaries.",
            "CMake must list all generated .cc files explicitly or by a safe glob policy.",
            (
                "If macros/init.mac contains /run/initialize, main.cc should execute "
                "the macro and omit the runManager initialize call token."
            ),
            (
                "main.cc should include ActionInitialization.hh and register the "
                "generated ActionInitialization rather than defining action classes."
            ),
            (
                "main.cc should match DetectorConstruction's generated constructor; "
                "pass an initialized MaterialRegistry when required."
            ),
        ],
    },
}


MODULE_INTERFACE_CONTEXT: dict[str, dict[str, Any]] = {
    "material": {
        "upstream_modules": [],
        "downstream_modules": ["geometry"],
        "provides": ["MaterialRegistry::GetMaterial", "MaterialRegistry::Initialize"],
        "consumes": ["G4ModelIR materials"],
    },
    "geometry": {
        "upstream_modules": ["material", "placement"],
        "downstream_modules": ["sensitive_detector", "main_cmake"],
        "provides": ["DetectorConstruction"],
        "consumes": ["MaterialRegistry", "PlacementManager", "G4ModelIR components"],
    },
    "placement": {
        "upstream_modules": [],
        "downstream_modules": ["geometry"],
        "provides": ["PlacementManager::PlaceVolume"],
        "consumes": ["G4ModelIR placement hierarchy"],
    },
    "source": {
        "upstream_modules": [],
        "downstream_modules": ["action_initialization"],
        "provides": ["PrimaryGeneratorAction"],
        "consumes": ["G4ModelIR sources"],
    },
    "physics": {
        "upstream_modules": [],
        "downstream_modules": ["main_cmake"],
        "provides": ["PhysicsListFactoryWrapper::CreatePhysicsList"],
        "consumes": ["G4ModelIR physics"],
    },
    "sensitive_detector": {
        "upstream_modules": ["geometry"],
        "downstream_modules": ["scoring"],
        "provides": ["SensitiveDetector", "Hit"],
        "consumes": ["logical volume names from geometry", "G4ModelIR sensitive_detectors"],
    },
    "scoring": {
        "upstream_modules": ["sensitive_detector", "geometry"],
        "downstream_modules": ["output_manager"],
        "provides": ["ScoringManager", "ScoringRecord"],
        "consumes": ["G4ModelIR scoring", "sensitive detector records or scoring meshes"],
    },
    "output_manager": {
        "upstream_modules": ["scoring", "source", "physics"],
        "downstream_modules": ["action_initialization"],
        "provides": ["OutputManager::BeginRun", "OutputManager::EndRun"],
        "consumes": ["ScoringManager results", "run metadata"],
    },
    "action_initialization": {
        "upstream_modules": ["source", "output_manager"],
        "downstream_modules": ["main_cmake"],
        "provides": ["ActionInitialization"],
        "consumes": ["PrimaryGeneratorAction", "OutputManager"],
    },
    "main_cmake": {
        "upstream_modules": MODULE_LAYER_ORDER[:-1],
        "downstream_modules": [],
        "provides": ["RadAgentG4 executable", "run macros"],
        "consumes": ["all generated headers, sources, and constructors"],
    },
}


def get_module_code_example(module_name: str) -> dict[str, Any]:
    return dict(MODULE_CODE_EXAMPLES.get(module_name, {}))


def get_module_interface_context(module_name: str) -> dict[str, Any]:
    return dict(MODULE_INTERFACE_CONTEXT.get(module_name, {}))


def build_context_retrieval_policy(
    *,
    rag_score: float | None = None,
    context_decision: str | None = None,
    web_search_available: bool | None = None,
) -> dict[str, Any]:
    """Describe how module agents should use RAG and web evidence."""
    score = 0.0 if rag_score is None else float(rag_score)
    return {
        "priority_order": ["module_context", "rag_snippets", "web_context"],
        "rag_required_when": [
            "Geant4 API ownership, constructor, macro command, or scoring API is uncertain",
            "upstream generated summaries do not expose the needed constructor or method",
            (
                "the IR requests a material, scorer, source, or geometry pattern not "
                "covered by examples"
            ),
        ],
        "web_allowed_when": [
            "RAG score is below 0.70",
            "RAG snippets do not cover the exact Geant4 API or macro command",
            "context_decision is allow_with_web_supplement",
        ],
        "web_constraints": [
            "Use trusted Geant4 documentation or CERN URLs first",
            "Record URLs in used_references for any web-derived API fact",
            "Do not invent APIs when neither RAG nor trusted web context supports them",
        ],
        "rag_score": score,
        "context_decision": context_decision or "unknown",
        "web_search_available": bool(web_search_available),
    }
