"""Plan C++ class architecture for the G4 project."""

from __future__ import annotations

import json
from typing import Any

from agent_core.g4_codegen.schemas import CodeArchitecturePlan

DEFAULT_CLASSES = [
    {
        "class_name": "DetectorConstruction",
        "header": "DetectorConstruction.hh",
        "source": "DetectorConstruction.cc",
        "responsibility": "Define geometry, materials, and sensitive detectors",
        "base_class": "G4VUserDetectorConstruction",
    },
    {
        "class_name": "MaterialRegistry",
        "header": "MaterialRegistry.hh",
        "source": "MaterialRegistry.cc",
        "responsibility": "Manage NIST and custom materials",
        "base_class": None,
    },
    {
        "class_name": "PlacementManager",
        "header": "PlacementManager.hh",
        "source": "PlacementManager.cc",
        "responsibility": "Manage physical volume placements",
        "base_class": None,
    },
    {
        "class_name": "PrimaryGeneratorAction",
        "header": "PrimaryGeneratorAction.hh",
        "source": "PrimaryGeneratorAction.cc",
        "responsibility": "Define particle source",
        "base_class": "G4VUserPrimaryGeneratorAction",
    },
    {
        "class_name": "PhysicsList",
        "header": "PhysicsList.hh",
        "source": "PhysicsList.cc",
        "responsibility": "Register physics processes",
        "base_class": "G4VModularPhysicsList",
    },
    {
        "class_name": "SensitiveDetector",
        "header": "SensitiveDetector.hh",
        "source": "SensitiveDetector.cc",
        "responsibility": "Handle hits in sensitive volumes",
        "base_class": "G4VSensitiveDetector",
    },
    {
        "class_name": "Hit",
        "header": "Hit.hh",
        "source": "Hit.cc",
        "responsibility": "Store hit data",
        "base_class": "G4VHit",
    },
    {
        "class_name": "ScoringManager",
        "header": "ScoringManager.hh",
        "source": "ScoringManager.cc",
        "responsibility": "Manage dose/edep scoring",
        "base_class": None,
    },
    {
        "class_name": "OutputManager",
        "header": "OutputManager.hh",
        "source": "OutputManager.cc",
        "responsibility": "Handle CSV/JSON output",
        "base_class": None,
    },
    {
        "class_name": "ActionInitialization",
        "header": "ActionInitialization.hh",
        "source": "ActionInitialization.cc",
        "responsibility": "Initialize all user actions",
        "base_class": "G4VUserActionInitialization",
    },
    {
        "class_name": "RunAction",
        "header": "RunAction.hh",
        "source": "RunAction.cc",
        "responsibility": "Begin/end of run actions",
        "base_class": "G4UserRunAction",
    },
    {
        "class_name": "EventAction",
        "header": "EventAction.hh",
        "source": "EventAction.cc",
        "responsibility": "Begin/end of event actions",
        "base_class": "G4UserEventAction",
    },
    {
        "class_name": "SteppingAction",
        "header": "SteppingAction.hh",
        "source": "SteppingAction.cc",
        "responsibility": "Per-step actions",
        "base_class": "G4UserSteppingAction",
    },
]


def plan_code_architecture(
    g4_model_ir: dict[str, Any],
    codegen_plan: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Plan C++ class structure based on model IR and codegen plan.

    Returns architecture plan with class definitions, file structure,
    and dependency mapping.
    """
    classes = list(DEFAULT_CLASSES)

    # Build file structure
    file_structure: dict[str, list[str]] = {
        "include": [c["header"] for c in classes],
        "src": [c["source"] for c in classes] + ["main.cc"],
        "macros": ["run.mac", "init.mac"],
        "root": ["CMakeLists.txt"],
    }

    # Build lifecycle mapping
    lifecycle = {
        "DetectorConstruction": "Construct()",
        "PrimaryGeneratorAction": "GeneratePrimaries()",
        "PhysicsList": "ConstructProcess()",
        "ActionInitialization": "Build()",
        "RunAction": "BeginOfRunAction() / EndOfRunAction()",
        "EventAction": "BeginOfEventAction() / EndOfEventAction()",
        "SteppingAction": "UserSteppingAction()",
    }

    # Build dependencies
    deps: dict[str, list[str]] = {
        "DetectorConstruction": ["MaterialRegistry", "PlacementManager", "SensitiveDetector"],
        "ActionInitialization": ["PrimaryGeneratorAction", "RunAction", "EventAction", "SteppingAction", "OutputManager"],
        "RunAction": ["OutputManager", "ScoringManager"],
        "EventAction": ["OutputManager"],
        "SteppingAction": ["ScoringManager"],
    }

    plan = CodeArchitecturePlan(
        classes=classes,
        file_structure=file_structure,
        lifecycle_mapping=lifecycle,
        dependencies=deps,
    )

    # Persist
    from agent_core.config.workspace import get_job_dir
    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)

    plan_path = codegen_dir / "code_architecture_plan.json"
    plan_path.write_text(
        json.dumps(plan.model_dump(), indent=2, ensure_ascii=False)
    )

    return plan.model_dump()
