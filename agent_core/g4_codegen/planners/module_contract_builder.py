"""Build module contracts for each G4 codegen module."""

from __future__ import annotations

import json
from typing import Any

from agent_core.g4_codegen.schemas import ModuleContract

MODULE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "material": {
        "module_type": "material",
        "responsibilities": [
            "Define NIST materials via G4NistManager",
            "Define custom materials",
            "Provide material lookup by name",
            "Material name mapping",
        ],
        "output_files": [
            "08_geant4/include/MaterialRegistry.hh",
            "08_geant4/src/MaterialRegistry.cc",
        ],
        "required_symbols": ["MaterialRegistry"],
        "dependencies": [],
        "forbidden_patterns": [
            "G4PVPlacement", "G4ParticleGun", "G4VSensitiveDetector",
        ],
    },
    "geometry": {
        "module_type": "geometry",
        "responsibilities": [
            "Define world volume",
            "Create solids (G4Box, G4Tubs, etc.)",
            "Create logical volumes",
            "Build component hierarchy",
        ],
        "output_files": [
            "08_geant4/include/DetectorConstruction.hh",
            "08_geant4/src/DetectorConstruction.cc",
        ],
        "required_symbols": ["DetectorConstruction"],
        "dependencies": ["material", "placement"],
        "forbidden_patterns": [
            "G4ParticleGun", "G4VSensitiveDetector",
        ],
    },
    "placement": {
        "module_type": "placement",
        "responsibilities": [
            "Manage G4PVPlacement instances",
            "Handle mother-child relationships",
            "Apply translations and rotations",
            "checkOverlaps configuration",
        ],
        "output_files": [
            "08_geant4/include/PlacementManager.hh",
            "08_geant4/src/PlacementManager.cc",
        ],
        "required_symbols": ["PlacementManager"],
        "dependencies": ["material"],
        "forbidden_patterns": [
            "G4ParticleGun", "G4VSensitiveDetector",
        ],
    },
    "source": {
        "module_type": "source",
        "responsibilities": [
            "Configure particle gun or GPS",
            "Set particle type, energy, direction",
            "Handle multi-source if needed",
        ],
        "output_files": [
            "08_geant4/include/PrimaryGeneratorAction.hh",
            "08_geant4/src/PrimaryGeneratorAction.cc",
        ],
        "required_symbols": ["PrimaryGeneratorAction"],
        "dependencies": [],
        "forbidden_patterns": [
            "G4PVPlacement", "G4VSensitiveDetector",
        ],
    },
    "physics": {
        "module_type": "physics",
        "responsibilities": [
            "Register physics list",
            "Configure EM/hadronic processes",
            "Set production cuts",
        ],
        "output_files": [
            "08_geant4/include/PhysicsList.hh",
            "08_geant4/src/PhysicsList.cc",
        ],
        "required_symbols": ["PhysicsList"],
        "dependencies": [],
        "forbidden_patterns": [
            "G4PVPlacement", "G4ParticleGun",
        ],
    },
    "sensitive_detector": {
        "module_type": "sensitive_detector",
        "responsibilities": [
            "Implement ProcessHits",
            "Define Hit class",
            "Register with G4SDManager",
            "Attach to logical volumes",
        ],
        "output_files": [
            "08_geant4/include/SensitiveDetector.hh",
            "08_geant4/src/SensitiveDetector.cc",
            "08_geant4/include/Hit.hh",
            "08_geant4/src/Hit.cc",
        ],
        "required_symbols": ["SensitiveDetector", "Hit"],
        "dependencies": [],
        "forbidden_patterns": [
            "G4ParticleGun",
        ],
    },
    "scoring": {
        "module_type": "scoring",
        "responsibilities": [
            "Manage dose/edep scoring",
            "Configure primitive scorers",
            "Handle mesh scoring",
            "Scoring output contract",
        ],
        "output_files": [
            "08_geant4/include/ScoringManager.hh",
            "08_geant4/src/ScoringManager.cc",
        ],
        "required_symbols": ["ScoringManager"],
        "dependencies": ["sensitive_detector"],
        "forbidden_patterns": [
            "G4ParticleGun",
        ],
    },
    "output_manager": {
        "module_type": "output_manager",
        "responsibilities": [
            "Handle CSV/JSON output",
            "Manage output package",
            "Run/event summary",
            "Metadata management",
        ],
        "output_files": [
            "08_geant4/include/OutputManager.hh",
            "08_geant4/src/OutputManager.cc",
        ],
        "required_symbols": ["OutputManager"],
        "dependencies": [],
        "forbidden_patterns": [
            "G4PVPlacement", "G4ParticleGun",
        ],
    },
    "action_initialization": {
        "module_type": "action_initialization",
        "responsibilities": [
            "Initialize all user actions",
            "Wire RunAction, EventAction, SteppingAction",
            "Connect PrimaryGeneratorAction",
            "Connect OutputManager",
        ],
        "output_files": [
            "08_geant4/include/ActionInitialization.hh",
            "08_geant4/src/ActionInitialization.cc",
            "08_geant4/include/RunAction.hh",
            "08_geant4/src/RunAction.cc",
            "08_geant4/include/EventAction.hh",
            "08_geant4/src/EventAction.cc",
            "08_geant4/include/SteppingAction.hh",
            "08_geant4/src/SteppingAction.cc",
        ],
        "required_symbols": ["ActionInitialization", "RunAction", "EventAction", "SteppingAction"],
        "dependencies": ["output_manager", "source"],
        "forbidden_patterns": [],
    },
    "main_cmake": {
        "module_type": "main_cmake",
        "responsibilities": [
            "Generate main.cc",
            "Generate CMakeLists.txt",
            "Generate run.mac and init.mac",
            "Directory structure",
        ],
        "output_files": [
            "08_geant4/main.cc",
            "08_geant4/CMakeLists.txt",
            "08_geant4/macros/run.mac",
            "08_geant4/macros/init.mac",
        ],
        "required_symbols": ["main"],
        "dependencies": [
            "material", "geometry", "placement", "source", "physics",
            "sensitive_detector", "scoring", "output_manager", "action_initialization",
        ],
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

    from agent_core.config.workspace import get_job_dir
    contracts_dir = get_job_dir(job_id) / "06_codegen" / "module_contracts"
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
            hard_gate_names=[f"{module_name}_hard_gate"],
            llm_gate_names=[f"{module_name}_llm_gate"],
        )

        contracts[module_name] = contract.model_dump()

        # Persist
        contract_path = contracts_dir / f"{module_name}.json"
        contract_path.write_text(
            json.dumps(contract.model_dump(), indent=2, ensure_ascii=False)
        )

    return contracts
