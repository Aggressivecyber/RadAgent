"""Integration Assembler — combines all generated modules into a buildable project.

Produces the proposed patch with all C++ files and a CMakeLists.txt.
"""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState


async def integration_assembler(state: G4CodegenSubgraphState) -> dict[str, Any]:
    """Assemble all code modules into a proposed patch.

    Reads individual module outputs from state, combines them into
    a single proposed_patch with changed_files list.
    """
    code_modules = state.get("code_modules", [])
    model_ir = state.get("g4_model_ir", {})
    errors = list(state.get("errors", []))

    # Collect all generated file content from state
    changed_files: list[dict[str, str]] = []

    # Each codegen node stores its output in state keys like:
    #   material_registry_code, geometry_code, etc.
    code_keys = [
        ("material_registry_code", "src/MaterialRegistry.cc"),
        ("material_registry_header", "include/MaterialRegistry.hh"),
        ("geometry_builder_code", "src/DetectorConstruction.cc"),
        ("geometry_builder_header", "include/DetectorConstruction.hh"),
        ("placement_code", "src/PlacementHelper.cc"),
        ("source_code", "src/PrimaryGeneratorAction.cc"),
        ("source_header", "include/PrimaryGeneratorAction.hh"),
        ("physics_macro", "macros/physics.mac"),
        ("sensitive_detector_code", "src/SensitiveDetector.cc"),
        ("sensitive_detector_header", "include/SensitiveDetector.hh"),
        ("scoring_code", "src/ScoringManager.cc"),
        ("output_manager_code", "src/OutputManager.cc"),
        ("output_manager_header", "include/OutputManager.hh"),
        ("main_code", "src/main.cc"),
        ("cmake_file", "CMakeLists.txt"),
    ]

    for key, path in code_keys:
        content: str = state.get(key, "") or ""  # type: ignore[assignment]
        if content:
            changed_files.append({
                "path": path,
                "content": content,
                "zone": "green",
            })

    # Generate CMakeLists.txt if not already provided
    if not state.get("cmake_file"):
        cmake_content = _generate_cmake(model_ir)
        changed_files.append({
            "path": "CMakeLists.txt",
            "content": cmake_content,
            "zone": "green",
        })

    # Generate minimal main.cc if not provided
    if not state.get("main_code"):
        main_content = _generate_main()
        changed_files.append({
            "path": "src/main.cc",
            "content": main_content,
            "zone": "green",
        })

    proposed_patch = {
        "patch_id": f"codegen_{state.get('job_id', 'unknown')}",
        "job_id": state.get("job_id", "unknown"),
        "description": f"Generated Geant4 code: {len(changed_files)} files",
        "change_type": "create",
        "risk_level": "low",
        "changed_files": changed_files,
        "test_plan": "cmake build + make",
        "expected_outputs": {"exit_code": 0},
    }

    has_code = len(changed_files) > 0
    if not has_code:
        errors.append("Integration assembler: no code modules generated")

    return {
        "proposed_patch": proposed_patch,
        "code_modules": code_modules,
        "errors": errors,
        "current_node": "integration_assembler",
    }


def _generate_cmake(model_ir: dict) -> str:
    """Generate a minimal CMakeLists.txt for the Geant4 project."""
    target = model_ir.get("target_system", "geant4_sim")
    safe_target = target.replace(" ", "_").replace("-", "_").lower()

    return f"""cmake_minimum_required(VERSION 3.16)
project({safe_target})

find_package(Geant4 REQUIRED)

file(GLOB sources src/*.cc)
file(GLOB headers include/*.hh)

add_executable({{safe_target}} ${{sources}})
target_include_directories({{safe_target}} PRIVATE include)
target_link_libraries({{safe_target}} ${{Geant4_LIBRARIES}})
"""


def _generate_main() -> str:
    """Generate a minimal main.cc entry point."""
    return '''#include "DetectorConstruction.hh"
#include "PhysicsList.hh"
#include "PrimaryGeneratorAction.hh"
#include "OutputManager.hh"

#include "G4RunManagerFactory.hh"
#include "G4UImanager.hh"

int main(int argc, char** argv) {
    auto* runManager = G4RunManagerFactory::CreateRunManager(
        G4RunManagerType::Serial);

    runManager->SetUserInitialization(new DetectorConstruction());
    runManager->SetUserInitialization(new PhysicsList());
    runManager->SetUserAction(new PrimaryGeneratorAction());

    runManager->Initialize();

    G4UImanager* uiManager = G4UImanager::GetUIpointer();
    if (argc > 1) {
        G4String command = "/control/execute ";
        G4String fileName = argv[1];
        uiManager->ApplyCommand(command + fileName);
    } else {
        runManager->BeamOn(1000);
    }

    delete runManager;
    return 0;
}
'''
