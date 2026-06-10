"""Module-owned code examples and interface context for G4 codegen agents."""

from __future__ import annotations

from typing import Any

MODULE_CODE_EXAMPLES: dict[str, dict[str, Any]] = {
    "simulation_core": {
        "owned_files": [
            "include/MaterialRegistry.hh",
            "src/MaterialRegistry.cc",
            "include/PlacementManager.hh",
            "src/PlacementManager.cc",
            "include/DetectorConstruction.hh",
            "src/DetectorConstruction.cc",
            "include/Hit.hh",
            "src/Hit.cc",
            "include/SensitiveDetector.hh",
            "src/SensitiveDetector.cc",
            "include/ScoringManager.hh",
            "src/ScoringManager.cc",
        ],
        "primary_symbols": [
            "MaterialRegistry",
            "PlacementManager",
            "DetectorConstruction",
            "Hit",
            "SensitiveDetector",
            "ScoringManager",
        ],
        "example": (
            "class DetectorConstruction : public G4VUserDetectorConstruction {\n"
            "public:\n"
            "  G4VPhysicalVolume* Construct() override;\n"
            "  void ConstructSDandField() override;\n"
            "  G4LogicalVolume* GetScoringVolume(const G4String& name) const;\n"
            "};\n"
            "class ScoringManager {\n"
            "public:\n"
            "  void RecordEnergyDeposit(G4int eventId, G4double edep, G4double dose);\n"
            "};\n"
        ),
        "notes": [
            "Generate material, geometry, placement, hit, sensitive detector, and "
            "scoring interfaces together.",
            "Attach sensitive detectors to actual logical volumes from DetectorConstruction.",
            "Keep scoring records and dose calculations tied to real geometry/material quantities.",
        ],
    },
    "beam_physics": {
        "owned_files": [
            "include/PrimaryGeneratorAction.hh",
            "src/PrimaryGeneratorAction.cc",
            "include/PhysicsListFactoryWrapper.hh",
            "src/PhysicsListFactoryWrapper.cc",
            "macros/physics_list.mac",
        ],
        "primary_symbols": ["PrimaryGeneratorAction", "PhysicsListFactoryWrapper"],
        "example": (
            "class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction {\n"
            "public:\n"
            "  void GeneratePrimaries(G4Event* event) override;\n"
            "};\n"
            "class PhysicsListFactoryWrapper {\n"
            "public:\n"
            "  G4VUserPhysicsList* CreatePhysicsList();\n"
            "};\n"
        ),
        "notes": [
            "Use IR source particle, energy, direction, position, and units exactly.",
            "Choose physics and production cuts based on the requested "
            "particle/material/scoring fidelity.",
        ],
    },
    "runtime_app": {
        "owned_files": [
            "include/OutputManager.hh",
            "src/OutputManager.cc",
            "include/ActionInitialization.hh",
            "src/ActionInitialization.cc",
            "include/RunAction.hh",
            "src/RunAction.cc",
            "include/EventAction.hh",
            "src/EventAction.cc",
            "include/SteppingAction.hh",
            "src/SteppingAction.cc",
            "CMakeLists.txt",
            "main.cc",
            "macros/run.mac",
            "macros/init.mac",
        ],
        "primary_symbols": [
            "OutputManager",
            "ActionInitialization",
            "RunAction",
            "EventAction",
            "SteppingAction",
            "main",
        ],
        "example": (
            "auto* runManager = new G4RunManager();\n"
            "runManager->SetUserInitialization(new DetectorConstruction());\n"
            "PhysicsListFactoryWrapper physics;\n"
            "runManager->SetUserInitialization(physics.CreatePhysicsList());\n"
            "runManager->SetUserInitialization(new ActionInitialization());\n"
        ),
        "notes": [
            "Read upstream summaries and use the actual generated class constructors and methods.",
            "Wire OutputManager through RunAction/EventAction/SteppingAction so "
            "event rows are real.",
            "CMake must include every generated source file needed by the final "
            "application and enable Geant4 UI/Vis/Qt support.",
            "main.cc should follow the B1 launch pattern: argc == 1 starts "
            "UIExecutive, otherwise execute argv[1] as a macro.",
        ],
    },
}


MODULE_INTERFACE_CONTEXT: dict[str, dict[str, Any]] = {
    "simulation_core": {
        "upstream_modules": [],
        "downstream_modules": ["runtime_app"],
        "provides": [
            "MaterialRegistry",
            "DetectorConstruction",
            "SensitiveDetector",
            "ScoringManager",
        ],
        "consumes": [
            "G4ModelIR materials",
            "G4ModelIR components",
            "G4ModelIR sensitive_detectors",
            "G4ModelIR scoring",
        ],
    },
    "beam_physics": {
        "upstream_modules": [],
        "downstream_modules": ["runtime_app"],
        "provides": ["PrimaryGeneratorAction", "PhysicsListFactoryWrapper"],
        "consumes": ["G4ModelIR sources", "G4ModelIR physics"],
    },
    "runtime_app": {
        "upstream_modules": ["simulation_core", "beam_physics"],
        "downstream_modules": [],
        "provides": ["RadAgentG4 executable", "run macros", "output artifact contract"],
        "consumes": [
            "simulation_core generated headers and constructors",
            "beam_physics generated headers and constructors",
            "runtime gate artifact contract",
        ],
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
