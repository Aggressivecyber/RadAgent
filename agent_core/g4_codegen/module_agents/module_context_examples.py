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
            "// CRITICAL lifetime rule: ScoringManager MUST be owned by the\n"
            "// DetectorConstruction and created in its CONSTRUCTOR, NOT in\n"
            "// ConstructSDandField(). Geant4 calls ActionInitialization::Build()\n"
            "// BEFORE ConstructSDandField(), so Build() must be able to fetch an\n"
            "// already-constructed, non-null ScoringManager for EventAction and\n"
            "// SteppingAction. If you `new` it inside ConstructSDandField(), those\n"
            "// actions get a null pointer and EVERY event records zero edep.\n"
            "class DetectorConstruction : public G4VUserDetectorConstruction {\n"
            "public:\n"
            "  DetectorConstruction() : fScoringManager(new ScoringManager()) {}\n"
            "  G4VPhysicalVolume* Construct() override;        // build geometry only\n"
            "  void ConstructSDandField() override;            // register regions + attach SDs\n"
            "  ScoringManager* GetScoringManager() const { return fScoringManager; }\n"
            "private:\n"
            "  ScoringManager* fScoringManager;  // constructed here, deleted in dtor\n"
            "};\n"
            "// SensitiveDetector records under its componentId (set via SetComponentId),\n"
            "// which MUST match the key passed to ScoringManager::RegisterRegionScoring.\n"
            "// Never use this->GetName() as the scoring key.\n"
            "class ScoringManager {\n"
            "public:\n"
            "  void RegisterRegionScoring(const G4String& componentId, G4LogicalVolume*);\n"
            "  void RegisterVoxelScoring(const G4String& componentId, G4LogicalVolume*,\n"
            "                            const std::array<G4double,3>& voxelSize_um);\n"
            "  void RecordEnergyDeposit(const G4String& componentId, G4double edep_MeV,\n"
            "                           const G4ThreeVector& position);\n"
            "  void EndOfEvent(const G4String& componentId, G4double& edep, G4double& dose);\n"
            "};\n"
        ),
        "notes": [
            "Generate material, geometry, placement, hit, sensitive detector, and "
            "scoring interfaces together.",
            "Attach sensitive detectors to actual logical volumes from DetectorConstruction.",
            "Keep scoring records and dose calculations tied to real geometry/material quantities.",
            "ScoringManager lifetime: construct it in the DetectorConstruction constructor "
            "(and delete in the destructor). RegisterRegionScoring/RegisterVoxelScoring and "
            "SD attachment happen in ConstructSDandField() where logical volumes exist. "
            "ActionInitialization::Build() runs BEFORE ConstructSDandField, so the instance "
            "must already exist for EventAction/SteppingAction to receive a non-null pointer.",
            "Scoring key contract: every RecordEnergyDeposit call (from both SensitiveDetector "
            "and SteppingAction) MUST use the componentId that RegisterRegionScoring used. "
            "Give SensitiveDetector a SetComponentId() and use it — never this->GetName().",
            "Dose units: dose_Gy = edep_MeV * 1.602176634e-13 (J/MeV) / mass_kg. "
            "G4LogicalVolume::GetMass() returns kg. Do NOT treat `edep_MeV * MeV` as joules — "
            "Geant4's internal energy unit is MeV, so `* MeV` leaves the value in MeV.",
            "Register voxel scoring for every component that needs a 3D dose/edep map, using "
            "the IR voxel size in um. Without RegisterVoxelScoring, edep_3d.csv/dose_3d.csv "
            "are empty and the data-contract gate fails on 'no non-zero bins'.",
            "Sanity invariant: a smoke run with at least one particle through a sensitive "
            "volume MUST produce non-zero total edep. If event_table.csv is all zeros, the "
            "scoring wiring is broken — re-check the lifetime + key rules above.",
            "Region pitfall (GeomMgt0002 crash): do NOT create a custom G4Region rooted at "
            "the world logical volume — Geant4 already makes the world the root of "
            "DefaultRegionForTheWorld, and a volume cannot be root for two regions. For "
            "region-based scoring, register non-world scoring volumes only, or reuse the "
            "default region / cuts instead of making new regions for the world.",
            "Overlap pitfall (Geom0003 crash): every daughter volume must lie FULLY inside "
            "its mother. G4Box takes HALF-lengths (pass full/2). The placement-time "
            "CheckOverlaps can pass while /run/initialize still flags an overlap, so verify "
            "containment arithmetically: daughter center +/- half-lengths must be within the "
            "mother's bounds in every axis.",
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
            "Particle-table timing pitfall (BeamPhys001 crash): the particle "
            "table is NOT populated when PrimaryGeneratorAction is constructed, "
            "so G4ParticleTable::FindParticle(\"electron\") in the constructor "
            "returns null and aborts with 'Particle not found'. Resolve the "
            "particle via its Definition() singleton (e.g. "
            "G4Electron::ElectronDefinition(), G4Proton::Proton(), "
            "G4Gamma::GammaDefinition()) which is always available, or look it "
            "up lazily in GeneratePrimaries() — never rely on FindParticle in "
            "the constructor without a Definition() fallback.",
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
            "macros/init_vis.mac",
            "macros/vis.mac",
            "macros/gui.mac",
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
            "ActionInitialization::Build() must obtain the ScoringManager from the "
            "DetectorConstruction (via GetScoringManager()) and pass the SAME pointer "
            "to RunAction, EventAction, and SteppingAction. This is only safe because "
            "DetectorConstruction creates its ScoringManager in its constructor; do not "
            "rely on ConstructSDandField() having run at Build() time.",
            "At EndOfEvent, EventAction iterates ScoringManager::GetRegionScorings() and "
            "calls EndOfEvent(componentId) per region to pull per-event (edep, dose); a "
            "non-null ScoringManager with zero regions means ConstructSDandField did not "
            "register any region — that is a bug.",
            "CMake must include every generated source file needed by the final "
            "application and enable Geant4 UI/Vis/Qt support.",
            "main.cc should follow the B1 launch pattern: argc == 1 starts "
            "UIExecutive and executes macros/init_vis.mac, otherwise execute argv[1] "
            "as a batch macro.",
            "Generate B2-style vis.mac trajectories/hits and optional gui.mac viewer "
            "buttons for the native visual workbench.",
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
