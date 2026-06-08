"""Test that hard gate rejects empty generated_files."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile


class TestHardGateRejectsEmptyGeneratedFiles:
    """Verify hard gate fails when generated_files is empty."""

    def test_empty_list_returns_fail(self) -> None:
        """Empty generated_files list should result in fail."""
        result = run_hard_gate_checks("test_module", [])

        assert result.status == "fail"
        assert any("empty" in e.lower() for e in result.errors)

    def test_non_empty_files_may_pass(self) -> None:
        """Non-empty generated_files with valid content should pass basic checks."""
        files = [
            GeneratedModuleFile(
                path="src/Test.cc",
                operation="create_or_replace",
                new_content='#include "Test.hh"\nint x = 1;\n',
                generated_by="test_module_agent",
                module_name="test_module",
                rationale="test",
            ),
            GeneratedModuleFile(
                path="include/Test.hh",
                operation="create_or_replace",
                new_content="#pragma once\nint x;\n",
                generated_by="test_module_agent",
                module_name="test_module",
                rationale="test",
            ),
        ]

        result = run_hard_gate_checks("test_module", files)
        # Should not fail due to empty files
        assert "generated_files is empty" not in " ".join(result.errors)

    def test_main_cmake_root_paths_are_valid(self) -> None:
        """main_cmake may generate root-level CMakeLists.txt and main.cc."""
        files = [
            GeneratedModuleFile(
                path="CMakeLists.txt",
                operation="create_or_replace",
                new_content=(
                    "cmake_minimum_required(VERSION 3.16)\n"
                    "project(RadAgentG4)\n"
                    "find_package(Geant4 REQUIRED)\n"
                    "add_executable(RadAgentG4 main.cc)\n"
                ),
                generated_by="main_cmake_module_agent",
                module_name="main_cmake",
                rationale="test",
            ),
            GeneratedModuleFile(
                path="main.cc",
                operation="create_or_replace",
                new_content='int main() { return 0; }\n',
                generated_by="main_cmake_module_agent",
                module_name="main_cmake",
                rationale="test",
            ),
        ]

        result = run_hard_gate_checks("main_cmake", files, module_status="generated")

        valid_path_checks = [c for c in result.checks if c["check"] == "valid_path"]
        assert valid_path_checks
        assert all(c["status"] == "pass" for c in valid_path_checks)

    def test_geant4_style_include_guard_is_valid(self) -> None:
        """Geant4 examples often use mixed-case *_h include guards."""
        files = [
            GeneratedModuleFile(
                path="include/DetectorConstruction.hh",
                operation="create_or_replace",
                new_content=(
                    "#ifndef DetectorConstruction_h\n"
                    "#define DetectorConstruction_h 1\n"
                    "class DetectorConstruction {};\n"
                    "#endif\n"
                ),
                generated_by="geometry_module_agent",
                module_name="geometry",
                rationale="test",
            )
        ]

        result = run_hard_gate_checks("geometry", files, module_status="generated")

        header_guard_checks = [c for c in result.checks if c["check"] == "header_guard"]
        assert header_guard_checks == [
            {
                "check": "header_guard",
                "status": "pass",
                "message": "Header must have #pragma once or include guard",
            }
        ]
