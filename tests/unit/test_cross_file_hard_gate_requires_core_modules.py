"""P0-5: cross_file_hard_gate checks 10 core modules are present."""

from __future__ import annotations

from agent_core.g4_codegen.integration.cross_file_hard_gate import (
    REQUIRED_MODULES,
    run_cross_file_hard_gate,
)


def _full_valid_patch() -> dict:
    """Build a patch with all 10 core modules."""
    files = [
        {"path": "CMakeLists.txt", "new_content": "cmake_minimum_required(VERSION 3.16)\nproject(t)\nfind_package(Geant4 REQUIRED)\nfile(GLOB s src/*.cc)\nadd_executable(app main.cc ${s})\n", "zone": "green", "module_name": "main_cmake", "generated_by": "m"},
        {"path": "main.cc", "new_content": "int main(){return 0;}", "zone": "green", "module_name": "main_cmake", "generated_by": "m"},
    ]
    for mod in REQUIRED_MODULES:
        if mod == "main_cmake":
            continue
        files.append({"path": f"include/{mod}.hh", "new_content": "#pragma once", "zone": "green", "module_name": mod, "generated_by": "m"})
        files.append({"path": f"src/{mod}.cc", "new_content": f'#include "{mod}.hh"', "zone": "green", "module_name": mod, "generated_by": "m"})
    return {"changed_files": files}


def test_all_modules_present_passes():
    result = run_cross_file_hard_gate(_full_valid_patch(), {}, "test_job")
    module_checks = [c for c in result["checks"] if c["check"] == "required_module_present"]
    failures = [c for c in module_checks if c["status"] == "fail"]
    assert len(failures) == 0


def test_missing_material_fails():
    patch = _full_valid_patch()
    patch["changed_files"] = [
        f for f in patch["changed_files"] if f.get("module_name") != "material"
    ]
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    assert result["status"] == "fail"
    assert any("material" in e for e in result["errors"])


def test_missing_source_fails():
    patch = _full_valid_patch()
    patch["changed_files"] = [
        f for f in patch["changed_files"] if f.get("module_name") != "source"
    ]
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    assert result["status"] == "fail"
    assert any("source" in e for e in result["errors"])


def test_missing_physics_fails():
    patch = _full_valid_patch()
    patch["changed_files"] = [
        f for f in patch["changed_files"] if f.get("module_name") != "physics"
    ]
    result = run_cross_file_hard_gate(patch, {}, "test_job")
    assert result["status"] == "fail"
    assert any("physics" in e for e in result["errors"])


def test_required_modules_list():
    """Verify all 10 core modules are required."""
    assert len(REQUIRED_MODULES) == 10
    assert "material" in REQUIRED_MODULES
    assert "geometry" in REQUIRED_MODULES
    assert "placement" in REQUIRED_MODULES
    assert "source" in REQUIRED_MODULES
    assert "physics" in REQUIRED_MODULES
    assert "sensitive_detector" in REQUIRED_MODULES
    assert "scoring" in REQUIRED_MODULES
    assert "output_manager" in REQUIRED_MODULES
    assert "action_initialization" in REQUIRED_MODULES
    assert "main_cmake" in REQUIRED_MODULES
