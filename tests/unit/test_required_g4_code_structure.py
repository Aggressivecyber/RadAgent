"""Tests for required Geant4 code structure — verifies Gate 5 compliance.

The codegen module planner must produce modules covering:
- src/*.cc and include/*.hh for all required classes
- CMakeLists.txt referencing src/
- DetectorConstruction, MaterialRegistry, GeometryContext
- Component builders (WorldBuilder, HousingBuilder, etc.)
- SensitiveDetectorBuilder, ScoringBuilder
- PrimaryGeneratorAction, RunAction, OutputManager
"""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.nodes.code_module_planner import code_module_planner


def _complex_model_ir() -> dict[str, Any]:
    """Return a complex model IR for structure tests."""
    return {
        "components": [
            {"component_id": "world", "component_type": "world"},
            {"component_id": "housing", "component_type": "volume"},
            {"component_id": "pcb", "component_type": "volume"},
            {"component_id": "sensor_stack", "component_type": "assembly"},
            {"component_id": "top_electrode", "component_type": "volume"},
            {"component_id": "oxide_layer", "component_type": "volume"},
            {"component_id": "silicon_bulk", "component_type": "volume"},
            {"component_id": "sensitive_region", "component_type": "volume"},
            {"component_id": "bottom_electrode", "component_type": "volume"},
        ],
        "scoring": [
            {"scoring_id": "edep_det", "scoring_type": "region"},
            {"scoring_id": "dose_3d", "scoring_type": "mesh"},
            {"scoring_id": "event_table", "scoring_type": "region"},
        ],
        "sources": [
            {"source_id": "proton", "particle_type": "proton"},
        ],
    }


class TestRequiredG4CodeStructure:
    """Verify code module planner produces complete Geant4 project structure."""

    async def test_planner_produces_core_modules(self) -> None:
        """Must produce all core Geant4 modules."""
        result = await code_module_planner({"g4_model_ir": _complex_model_ir()})
        modules = result["code_modules"]
        module_ids = {m["module_id"] for m in modules}

        # Core modules that MUST exist
        required_core = {
            "detector_construction",
            "material_registry",
            "physics_list",
            "primary_generator",
            "output_manager",
            "main",
        }
        for req in required_core:
            assert req in module_ids, f"Missing core module: {req}"

    async def test_planner_produces_component_builders(self) -> None:
        """Must produce builder modules for each non-world component."""
        result = await code_module_planner({"g4_model_ir": _complex_model_ir()})
        modules = result["code_modules"]
        module_ids = {m["module_id"] for m in modules}

        # Component-specific geometry builders
        assert "geometry_housing" in module_ids
        assert "geometry_pcb" in module_ids
        assert "geometry_silicon_bulk" in module_ids

    async def test_planner_produces_scoring_modules(self) -> None:
        """Must produce scoring/sensitive detector modules."""
        result = await code_module_planner({"g4_model_ir": _complex_model_ir()})
        modules = result["code_modules"]
        module_ids = {m["module_id"] for m in modules}

        # Scoring modules
        assert "sd_edep_det" in module_ids
        assert "sd_dose_3d" in module_ids
        assert "sd_event_table" in module_ids

    async def test_modules_have_source_and_header(self) -> None:
        """Each module must specify source and header file paths."""
        result = await code_module_planner({"g4_model_ir": _complex_model_ir()})
        modules = result["code_modules"]

        for mod in modules:
            target = mod.get("target_file", "")
            header = mod.get("target_header", "")
            # Core modules must have both src/ and include/ paths
            if mod["module_id"] in ("main",):
                continue  # main.cc has no separate header
            if target:
                assert target.startswith("src/"), f"Module {mod['module_id']}: target not in src/"
            if header:
                assert header.startswith("include/"), (
                    f"Module {mod['module_id']}: header not in include/"
                )

    def test_new_integration_assembler_generates_cmake(self) -> None:
        """P0-12: New integration assembler must produce CMakeLists.txt."""
        from agent_core.g4_codegen.integration.integration_assembler import (
            assemble_proposed_patch,
        )

        module_results = {
            "main_cmake": {
                "status": "generated",
                "generated_files": [
                    {
                        "path": "CMakeLists.txt",
                        "new_content": "cmake_minimum_required(VERSION 3.16)\n",
                        "generated_by": "main_cmake_module_agent",
                        "module_name": "main_cmake",
                        "rationale": "test",
                    },
                    {
                        "path": "main.cc",
                        "new_content": "int main(){return 0;}\n",
                        "generated_by": "main_cmake_module_agent",
                        "module_name": "main_cmake",
                        "rationale": "test",
                    },
                ],
            },
        }
        gates = {
            "main_cmake": {"hard": {"status": "pass"}, "llm": {"status": "pass"}},
        }
        patch = assemble_proposed_patch(module_results, gates, "struct_test")
        paths = [f["path"] for f in patch["changed_files"]]
        assert "CMakeLists.txt" in paths

    async def test_cmake_structure_validates(self) -> None:
        """CMake validator must accept well-structured CMakeLists.txt."""
        from agent_core.g4_codegen.validators.cmake_structure import (
            validate_cmake_structure,
        )

        cmake = """cmake_minimum_required(VERSION 3.16)
project(rad_detector)
find_package(Geant4 REQUIRED)
file(GLOB sources src/*.cc)
add_executable(rad_detector ${sources})
target_include_directories(rad_detector PRIVATE include)
target_link_libraries(rad_detector ${Geant4_LIBRARIES})
"""
        valid, issues = validate_cmake_structure(cmake)
        assert valid, f"CMake validation failed: {issues}"

    async def test_cmake_missing_geant4_fails(self) -> None:
        """CMake without Geant4 must fail validation."""
        from agent_core.g4_codegen.validators.cmake_structure import (
            validate_cmake_structure,
        )

        cmake = "cmake_minimum_required(VERSION 3.16)\nproject(test)\n"
        valid, issues = validate_cmake_structure(cmake)
        assert not valid
        assert any("Geant4" in i for i in issues)

    async def test_no_physics_list_custom_class_required(self) -> None:
        """Standard physics list (e.g. QGSP_BIC_HP) needs no custom PhysicsList."""
        result = await code_module_planner({"g4_model_ir": _complex_model_ir()})
        modules = result["code_modules"]
        module_ids = {m["module_id"] for m in modules}

        # physics_list module should exist but it's a reference, not a custom class
        assert "physics_list" in module_ids

    async def test_sensitive_detector_without_stepping_action(self) -> None:
        """SensitiveDetector + ScoringBuilder without SteppingAction should be allowed."""
        result = await code_module_planner({"g4_model_ir": _complex_model_ir()})
        modules = result["code_modules"]
        module_ids = {m["module_id"] for m in modules}

        # Sensitive detector modules should exist
        scoring_modules = [m for m in module_ids if m.startswith("sd_")]
        assert len(scoring_modules) >= 1

        # SteppingAction is NOT required when using SensitiveDetector
        # (no assertion needed — absence of stepping modules is acceptable)
