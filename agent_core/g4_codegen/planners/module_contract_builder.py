"""Build module contracts for each G4 codegen module."""

from __future__ import annotations

import json
from typing import Any

from agent_core.g4_codegen.schemas import ModuleContract
from agent_core.workspace.paths import STAGE_CODEGEN

# P0-2: All paths are relative to geant4_project (no geant4_project/ prefix).
# file_access_policy allows: include/*.hh, src/*.cc, macros/*.mac,
# CMakeLists.txt, main.cc — all relative to generated_code_dir (geant4_project).
MODULE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "simulation_core": {
        "module_type": "simulation_core",
        "responsibilities": [
            "Define materials and material lookup used by the whole Geant4 project",
            "Build the full detector/world geometry from G4ModelIR without "
            "unauthorized simplification",
            "Create placements, rotations, overlap policy, and logical volume accessors coherently",
            "Implement hit, sensitive detector, and scoring data structures as one aligned model",
            "Attach sensitive detectors and scoring paths consistently with the generated geometry",
            "Represent dose/edep scoring with explicit transport precision choices "
            "such as range cuts, step limits, or production cuts when required by "
            "the scenario",
        ],
        "output_files": [
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
        "required_symbols": [
            "MaterialRegistry",
            "PlacementManager",
            "DetectorConstruction",
            "Hit",
            "SensitiveDetector",
            "ScoringManager",
        ],
        "dependencies": [],
        "forbidden_patterns": [],
    },
    "beam_physics": {
        "module_type": "beam_physics",
        "responsibilities": [
            "Generate the primary particle source from G4ModelIR source requirements",
            "Select and configure an appropriate Geant4 physics list from the "
            "requested physics model",
            "Set production cuts and transport controls needed for the requested scoring fidelity",
            "Keep source units, direction, spatial distribution, and particle "
            "identity faithful to the requirement",
        ],
        "output_files": [
            "include/PrimaryGeneratorAction.hh",
            "src/PrimaryGeneratorAction.cc",
            "include/PhysicsListFactoryWrapper.hh",
            "src/PhysicsListFactoryWrapper.cc",
            "macros/physics_list.mac",
        ],
        "required_symbols": [
            "PrimaryGeneratorAction",
            "PhysicsListFactoryWrapper",
        ],
        "dependencies": [],
        "forbidden_patterns": [],
    },
    "runtime_app": {
        "module_type": "runtime_app",
        "responsibilities": [
            "Wire detector construction, physics, source, actions, scoring, and "
            "output into a runnable application",
            "Generate run/event/stepping actions and output manager with real event "
            "rows and scoring artifacts",
            "Generate main.cc, CMakeLists.txt, run.mac, and init.mac from the "
            "actual generated interfaces",
            "Configure CMake for Geant4 UI/Vis/Qt support so the executable can "
            "open the Geant4 interactive UI",
            "Follow the Geant4 B1-style launch contract: no script argument opens "
            "interactive UI; a macro script argument runs batch mode",
            "Write runtime artifacts to G4_OUTPUT_DIR when set, falling back only "
            "when the environment variable is absent",
            "Preserve the smoke artifact contract with g4_summary.json, "
            "provenance.json, event_table.csv, edep_3d.csv, and dose_3d.csv",
            "Ensure event_table.csv has EventID,edep_MeV,dose_Gy rows and "
            "edep/dose mesh CSVs contain non-zero physical quantities",
        ],
        "output_files": [
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
            "main.cc",
            "CMakeLists.txt",
            "macros/run.mac",
            "macros/init.mac",
        ],
        "required_symbols": [
            "OutputManager",
            "ActionInitialization",
            "RunAction",
            "EventAction",
            "SteppingAction",
            "main",
        ],
        "dependencies": ["simulation_core", "beam_physics"],
        "forbidden_patterns": [],
    },
}


def build_module_contracts(
    g4_model_ir: dict[str, Any],
    codegen_plan: dict[str, Any],
    job_id: str,
) -> dict[str, dict[str, Any]]:
    """Build module contracts for all required modules.

    Returns dict mapping module_name -> contract dict.
    """
    required = codegen_plan.get("required_modules", list(MODULE_DEFINITIONS.keys()))
    contracts: dict[str, dict[str, Any]] = {}

    from agent_core.workspace.io import get_job_dir

    contracts_dir = get_job_dir(job_id) / STAGE_CODEGEN / "module_contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)

    for module_name in required:
        defn = MODULE_DEFINITIONS.get(module_name)
        if not defn:
            continue

        contract = ModuleContract(
            module_name=module_name,
            module_type=defn["module_type"],
            responsibilities=defn["responsibilities"],
            input_ir_paths=["g4_model_ir"],
            output_files=defn["output_files"],
            required_symbols=defn["required_symbols"],
            dependencies=defn["dependencies"],
            forbidden_patterns=defn["forbidden_patterns"],
        )

        contracts[module_name] = contract.model_dump()

        # Persist
        contract_path = contracts_dir / f"{module_name}.json"
        contract_path.write_text(json.dumps(contract.model_dump(), indent=2, ensure_ascii=False))

    return contracts
