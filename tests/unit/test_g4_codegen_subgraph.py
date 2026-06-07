"""Tests for G4 Codegen Subgraph — compilation, nodes, and validators."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class TestG4CodegenSubgraphCompilation:
    """Verify the G4 codegen subgraph compiles."""

    def test_subgraph_compiles(self) -> None:
        """G4 codegen subgraph must compile without errors."""
        from agent_core.graph.subgraphs.g4_codegen_graph import (
            build_g4_codegen_subgraph,
        )

        graph = build_g4_codegen_subgraph()
        compiled = graph.compile()
        assert compiled is not None

    def test_subgraph_state_schema(self) -> None:
        """Subgraph state must have required fields."""
        from agent_core.g4_codegen.schemas import G4CodegenSubgraphState

        annotations = G4CodegenSubgraphState.__annotations__
        required = ["job_id", "g4_model_ir_path", "proposed_patch", "g4_codegen_status"]
        for field in required:
            assert field in annotations, f"Missing field: {field}"


class TestCodeModulePlanner:
    """Test the code module planner node."""

    async def test_plans_modules_from_model_ir(self) -> None:
        """Should plan modules based on components and scoring."""
        from agent_core.g4_codegen.nodes.code_module_planner import code_module_planner

        state = {
            "g4_model_ir": {
                "components": [
                    {"component_id": "world", "component_type": "world"},
                    {"component_id": "silicon_det", "component_type": "volume"},
                ],
                "scoring": [
                    {"scoring_id": "edep", "scoring_type": "region"},
                ],
            },
        }
        result = await code_module_planner(state)

        modules = result["code_modules"]
        module_ids = [m["module_id"] for m in modules]

        # Always-present modules
        assert "detector_construction" in module_ids
        assert "material_registry" in module_ids
        assert "physics_list" in module_ids
        assert "primary_generator" in module_ids
        assert "output_manager" in module_ids
        assert "main" in module_ids

        # Component-specific module
        assert "geometry_silicon_det" in module_ids

        # Sensitive detector module
        assert "sd_edep" in module_ids

    async def test_empty_model_ir(self) -> None:
        """Empty model IR should still produce core modules."""
        from agent_core.g4_codegen.nodes.code_module_planner import code_module_planner

        result = await code_module_planner({"g4_model_ir": {}})
        modules = result["code_modules"]
        assert len(modules) >= 6  # core modules only


class TestIntegrationAssembler:
    """Test the integration assembler node."""

    async def test_assembles_patch_from_code(self) -> None:
        """Should assemble proposed_patch from individual code outputs."""
        from agent_core.g4_codegen.nodes.integration_assembler import (
            integration_assembler,
        )

        state: dict[str, Any] = {
            "job_id": "test",
            "code_modules": [{"module_id": "main"}],
            "g4_model_ir": {"target_system": "test_sim"},
            "errors": [],
            "main_code": "int main() { return 0; }",
            "cmake_file": "cmake_minimum_required(VERSION 3.16)\nproject(test)",
        }
        result = await integration_assembler(state)

        assert result["current_node"] == "integration_assembler"
        patch = result["proposed_patch"]
        assert "changed_files" in patch
        assert len(patch["changed_files"]) >= 1

    async def test_generates_cmake_if_missing(self) -> None:
        """Should generate CMakeLists.txt if not provided."""
        from agent_core.g4_codegen.nodes.integration_assembler import (
            integration_assembler,
        )

        state: dict[str, Any] = {
            "job_id": "test",
            "code_modules": [],
            "g4_model_ir": {},
            "errors": [],
        }
        result = await integration_assembler(state)

        patch = result["proposed_patch"]
        paths = [f["path"] for f in patch["changed_files"]]
        assert "CMakeLists.txt" in paths


class TestCodegenValidators:
    """Test g4_codegen validators."""

    def test_code_module_boundary_valid(self) -> None:
        """Valid module with clean boundaries should pass."""
        from agent_core.g4_codegen.validators.code_module_boundary import (
            validate_code_module_boundary,
        )

        code = '#include "MyModule.hh"\nvoid myFunction() {}\n'
        header = "include/MyModule.hh"
        valid, issues = validate_code_module_boundary("my_module", code, header)
        assert valid, f"Unexpected issues: {issues}"

    def test_code_module_boundary_empty_code(self) -> None:
        """Empty code should fail validation."""
        from agent_core.g4_codegen.validators.code_module_boundary import (
            validate_code_module_boundary,
        )

        valid, issues = validate_code_module_boundary("empty_mod", "", "")
        assert not valid
        assert any("empty" in i for i in issues)

    def test_no_magic_number_clean(self) -> None:
        """Code with named constants should pass."""
        from agent_core.g4_codegen.validators.no_magic_number import check_magic_numbers

        code = 'constexpr double WIDTH = 100.0;\nauto box = new G4Box("b", WIDTH, WIDTH, WIDTH);'
        clean, violations = check_magic_numbers(code, "test")
        assert clean, f"Unexpected violations: {violations}"

    def test_no_magic_number_detects_literal(self) -> None:
        """Code with raw numeric literals should be flagged."""
        from agent_core.g4_codegen.validators.no_magic_number import check_magic_numbers

        code = 'auto box = new G4Box("b", 42.5, 42.5, 42.5);'
        clean, violations = check_magic_numbers(code, "test")
        assert not clean
        assert len(violations) > 0

    def test_cmake_structure_valid(self) -> None:
        """Valid CMakeLists.txt should pass."""
        from agent_core.g4_codegen.validators.cmake_structure import (
            validate_cmake_structure,
        )

        cmake = """cmake_minimum_required(VERSION 3.16)
project(test_sim)
find_package(Geant4 REQUIRED)
file(GLOB sources src/*.cc)
add_executable(test_sim ${sources})
target_include_directories(test_sim PRIVATE include)
target_link_libraries(test_sim ${Geant4_LIBRARIES})
"""
        valid, issues = validate_cmake_structure(cmake)
        assert valid, f"Unexpected issues: {issues}"

    def test_cmake_structure_missing_geant4(self) -> None:
        """CMake without Geant4 should fail."""
        from agent_core.g4_codegen.validators.cmake_structure import (
            validate_cmake_structure,
        )

        cmake = "cmake_minimum_required(VERSION 3.16)\nproject(test)\n"
        valid, issues = validate_cmake_structure(cmake)
        assert not valid
        assert any("Geant4" in i for i in issues)


class TestLoadModelIr:
    """Test the codegen I/O functions."""

    async def test_load_from_file(self, tmp_path: Path) -> None:
        """Should load model IR from JSON file."""
        from agent_core.g4_codegen import load_model_ir

        ir_file = tmp_path / "ir.json"
        ir_file.write_text(json.dumps({"model_ir_id": "test", "components": []}))

        result = await load_model_ir({"g4_model_ir_path": str(ir_file)})
        assert result["g4_model_ir"]["model_ir_id"] == "test"

    async def test_load_missing_file(self) -> None:
        """Missing file should return empty model IR."""
        from agent_core.g4_codegen import load_model_ir

        result = await load_model_ir({"g4_model_ir_path": "/nonexistent/ir.json"})
        assert result["g4_model_ir"] == {}
