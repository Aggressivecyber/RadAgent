"""Code Module Planner — plans which C++ modules to generate from Model IR.

Reads the Model IR components and produces a code_module_plan listing
every module that the codegen pipeline will generate.
"""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState


async def code_module_planner(state: G4CodegenSubgraphState) -> dict[str, Any]:
    """Plan code modules from Model IR.

    Produces a code_module_plan with module names, dependencies, and
    target file paths. Each module corresponds to exactly one codegen node.
    """
    model_ir = state.get("g4_model_ir", {})
    components = model_ir.get("components", [])
    scoring = model_ir.get("scoring", [])

    # Always-generated modules
    modules = [
        {
            "module_id": "detector_construction",
            "target_file": "src/DetectorConstruction.cc",
            "target_header": "include/DetectorConstruction.hh",
            "description": "Main detector geometry construction",
            "depends_on": [],
        },
        {
            "module_id": "material_registry",
            "target_file": "src/MaterialRegistry.cc",
            "target_header": "include/MaterialRegistry.hh",
            "description": "Material definitions (NIST + custom)",
            "depends_on": [],
        },
        {
            "module_id": "physics_list",
            "target_file": "src/PhysicsList.cc",
            "target_header": "include/PhysicsList.hh",
            "description": "Physics list configuration",
            "depends_on": [],
        },
        {
            "module_id": "primary_generator",
            "target_file": "src/PrimaryGeneratorAction.cc",
            "target_header": "include/PrimaryGeneratorAction.hh",
            "description": "Particle source / beam configuration",
            "depends_on": [],
        },
    ]

    # Component-specific geometry modules
    comp_deps = ["material_registry"]
    for comp in components:
        if comp.get("component_type") == "world":
            continue  # world is part of DetectorConstruction
        cid = comp.get("component_id", "unknown")
        safe_name = cid.replace("-", "_").replace(" ", "_")
        modules.append(
            {
                "module_id": f"geometry_{safe_name}",
                "target_file": f"src/Geometry_{safe_name}.cc",
                "target_header": f"include/Geometry_{safe_name}.hh",
                "description": f"Geometry for {comp.get('display_name', cid)}",
                "depends_on": comp_deps,
            }
        )

    # Sensitive detector modules (one per scoring region)
    for sc in scoring:
        sc_id = sc.get("scoring_id", "unknown")
        safe_name = sc_id.replace("-", "_").replace(" ", "_")
        modules.append(
            {
                "module_id": f"sd_{safe_name}",
                "target_file": f"src/SensitiveDetector_{safe_name}.cc",
                "target_header": f"include/SensitiveDetector_{safe_name}.hh",
                "description": f"Sensitive detector for {sc.get('scoring_type', '?')} scoring",
                "depends_on": ["detector_construction"],
            }
        )

    # Output manager
    modules.append(
        {
            "module_id": "output_manager",
            "target_file": "src/OutputManager.cc",
            "target_header": "include/OutputManager.hh",
            "description": "Output file management (CSV/ROOT)",
            "depends_on": ["detector_construction"],
        }
    )

    # Main entry point
    modules.append(
        {
            "module_id": "main",
            "target_file": "src/main.cc",
            "target_header": "",
            "description": "Program entry point",
            "depends_on": [
                "detector_construction",
                "physics_list",
                "primary_generator",
                "output_manager",
            ],
        }
    )

    return {
        "code_modules": modules,
        "current_node": "code_module_planner",
    }
