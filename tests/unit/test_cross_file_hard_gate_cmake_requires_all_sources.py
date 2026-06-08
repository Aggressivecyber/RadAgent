"""P0-4: cross_file_hard_gate checks CMakeLists.txt includes all src/*.cc."""

from __future__ import annotations

from agent_core.g4_codegen.integration.cross_file_hard_gate import (
    run_cross_file_hard_gate,
)


def _base_files() -> list[dict]:
    """Minimal set of files for a valid patch."""
    return [
        {
            "path": "CMakeLists.txt",
            "new_content": "",
            "zone": "green",
            "module_name": "main_cmake",
            "generated_by": "main_cmake_module_agent",
        },
        {
            "path": "main.cc",
            "new_content": "int main(){return 0;}",
            "zone": "green",
            "module_name": "main_cmake",
            "generated_by": "main_cmake_module_agent",
        },
        {
            "path": "include/MaterialRegistry.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "material",
            "generated_by": "material_module_agent",
        },
        {
            "path": "src/MaterialRegistry.cc",
            "new_content": '#include "MaterialRegistry.hh"',
            "zone": "green",
            "module_name": "material",
            "generated_by": "material_module_agent",
        },
        {
            "path": "include/DetectorConstruction.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "geometry",
            "generated_by": "geometry_module_agent",
        },
        {
            "path": "src/DetectorConstruction.cc",
            "new_content": '#include "DetectorConstruction.hh"',
            "zone": "green",
            "module_name": "geometry",
            "generated_by": "geometry_module_agent",
        },
        {
            "path": "include/PlacementManager.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "placement",
            "generated_by": "placement_module_agent",
        },
        {
            "path": "src/PlacementManager.cc",
            "new_content": '#include "PlacementManager.hh"',
            "zone": "green",
            "module_name": "placement",
            "generated_by": "placement_module_agent",
        },
        {
            "path": "include/PrimaryGeneratorAction.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "source",
            "generated_by": "source_module_agent",
        },
        {
            "path": "src/PrimaryGeneratorAction.cc",
            "new_content": '#include "PrimaryGeneratorAction.hh"',
            "zone": "green",
            "module_name": "source",
            "generated_by": "source_module_agent",
        },
        {
            "path": "include/PhysicsListFactoryWrapper.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "physics",
            "generated_by": "physics_module_agent",
        },
        {
            "path": "src/PhysicsListFactoryWrapper.cc",
            "new_content": '#include "PhysicsListFactoryWrapper.hh"',
            "zone": "green",
            "module_name": "physics",
            "generated_by": "physics_module_agent",
        },
        {
            "path": "macros/physics_list.mac",
            "new_content": "/run/initialize",
            "zone": "green",
            "module_name": "physics",
            "generated_by": "physics_module_agent",
        },
        {
            "path": "include/SensitiveDetector.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "sensitive_detector",
            "generated_by": "sensitive_detector_module_agent",
        },
        {
            "path": "src/SensitiveDetector.cc",
            "new_content": '#include "SensitiveDetector.hh"',
            "zone": "green",
            "module_name": "sensitive_detector",
            "generated_by": "sensitive_detector_module_agent",
        },
        {
            "path": "include/ScoringManager.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "scoring",
            "generated_by": "scoring_module_agent",
        },
        {
            "path": "src/ScoringManager.cc",
            "new_content": '#include "ScoringManager.hh"',
            "zone": "green",
            "module_name": "scoring",
            "generated_by": "scoring_module_agent",
        },
        {
            "path": "include/OutputManager.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "output_manager",
            "generated_by": "output_manager_module_agent",
        },
        {
            "path": "src/OutputManager.cc",
            "new_content": '#include "OutputManager.hh"',
            "zone": "green",
            "module_name": "output_manager",
            "generated_by": "output_manager_module_agent",
        },
        {
            "path": "include/ActionInitialization.hh",
            "new_content": "#pragma once",
            "zone": "green",
            "module_name": "action_initialization",
            "generated_by": "action_initialization_module_agent",
        },
        {
            "path": "src/ActionInitialization.cc",
            "new_content": '#include "ActionInitialization.hh"',
            "zone": "green",
            "module_name": "action_initialization",
            "generated_by": "action_initialization_module_agent",
        },
    ]


def test_cmake_missing_source_fails():
    """CMakeLists.txt that doesn't include a source file must fail."""
    files = _base_files()
    # Set CMake content that doesn't include MaterialRegistry.cc
    files[0]["new_content"] = (
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(test)\n"
        "find_package(Geant4 REQUIRED)\n"
        "add_executable(app main.cc src/DetectorConstruction.cc)\n"
    )
    result = run_cross_file_hard_gate({"changed_files": files}, {}, "test_job")
    assert result["status"] == "fail"
    assert any("MaterialRegistry" in e for e in result["errors"])


def test_cmake_includes_all_sources_passes():
    """CMakeLists.txt that explicitly includes all sources must pass."""
    files = _base_files()
    # Gate checks for filename presence — must list sources explicitly
    src_names = [f["path"].split("/")[-1] for f in files if f["path"].startswith("src/")]
    files[0]["new_content"] = (
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(test)\n"
        "find_package(Geant4 REQUIRED)\n"
        "add_executable(app main.cc " + " ".join(src_names) + ")\n"
    )
    result = run_cross_file_hard_gate({"changed_files": files}, {}, "test_job")
    cmake_check = [c for c in result["checks"] if c["check"] == "cmake_includes_source"]
    failures = [c for c in cmake_check if c["status"] == "fail"]
    assert len(failures) == 0
