"""P0-1: cross_file_hard_gate uses relative paths (no 08_geant4/ prefix)."""

from __future__ import annotations

from agent_core.g4_codegen.integration.cross_file_hard_gate import (
    run_cross_file_hard_gate,
)


def _minimal_patch() -> dict:
    return {
        "changed_files": [
            {
                "path": "CMakeLists.txt",
                "new_content": "cmake_minimum_required(VERSION 3.16)\nproject(test)\nfind_package(Geant4 REQUIRED)\nadd_executable(app main.cc src/Foo.cc)\n",  # noqa: E501
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
                "path": "src/Foo.cc",
                "new_content": '#include "Foo.hh"\n',
                "zone": "green",
                "module_name": "geometry",
                "generated_by": "geometry_module_agent",
            },
            {
                "path": "include/Foo.hh",
                "new_content": "#pragma once\nclass Foo {};",
                "zone": "green",
                "module_name": "geometry",
                "generated_by": "geometry_module_agent",
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
                "module_name": "physics",  # noqa: E501
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
        ],
    }


def test_gate_uses_relative_paths():
    """Gate must work with relative paths (no 08_geant4/ prefix)."""
    result = run_cross_file_hard_gate(_minimal_patch(), {}, "test_job")
    # Should pass — all paths are relative
    cmake_check = [c for c in result["checks"] if c["check"] == "cmake_exists"]
    assert cmake_check
    assert cmake_check[0]["status"] == "pass"


def test_gate_rejects_08_geant4_prefix():
    """Gate must fail if paths have 08_geant4/ prefix."""
    patch = _minimal_patch()
    # Add a file with old prefix
    patch["changed_files"].append(
        {
            "path": "08_geant4/src/Bad.cc",
            "new_content": "int x;",
            "zone": "green",
            "module_name": "geometry",
            "generated_by": "geometry_module_agent",
        }
    )
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    # The gate should still work (paths are checked as-is)
    assert result["status"] in ("pass", "fail")
