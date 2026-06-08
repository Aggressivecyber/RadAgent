"""Test that assemble_proposed_patch output satisfies PatchValidator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agent_core.g4_codegen.global_repair import run_global_code_repair
from agent_core.g4_codegen.integration.integration_assembler import assemble_proposed_patch
from agent_core.validators.patch_validator import PatchValidator


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


def _make_module_result(
    module_name: str,
    files: list[dict[str, str]],
    status: str = "generated",
) -> dict[str, Any]:
    """Build a module result dict matching ModuleAgentResult.model_dump()."""
    generated_files = []
    for f in files:
        generated_files.append(
            {
                "path": f["path"],
                "operation": f.get("operation", "create_or_replace"),
                "new_content": f["new_content"],
                "generated_by": f.get("generated_by", f"{module_name}_module_agent"),
                "module_name": f.get("module_name", module_name),
                "rationale": f.get("rationale", "test"),
                "dependencies": f.get("dependencies", []),
                "satisfies": f.get("satisfies", []),
                "risk_notes": f.get("risk_notes", []),
                "used_references": f.get("used_references", []),
            }
        )
    return {
        "module_name": module_name,
        "status": status,
        "generated_files": generated_files,
        "errors": [],
        "warnings": [],
    }


def _make_gate_results_pass(module_names: list[str]) -> dict[str, dict[str, Any]]:
    """Build gate results where all modules pass both gates."""
    results = {}
    for name in module_names:
        results[name] = {
            "hard": {"status": "pass", "checks": [], "errors": []},
            "llm": {"status": "pass", "checks": [], "errors": []},
        }
    return results


class TestAssembleProposedPatchPatchValidatorContract:
    """Verify that assemble_proposed_patch output passes PatchValidator."""

    def test_patch_satisfies_validator(self, workspace: Path) -> None:
        """assemble_proposed_patch output must satisfy PatchValidator."""
        module_results = {
            "material": _make_module_result(
                "material",
                [
                    {
                        "path": "src/MaterialRegistry.cc",
                        "new_content": '#include "MaterialRegistry.hh"\nvoid MaterialRegistry::DefineMaterials() {}',  # noqa: E501
                    },
                ],
            ),
            "geometry": _make_module_result(
                "geometry",
                [
                    {
                        "path": "src/DetectorConstruction.cc",
                        "new_content": '#include "DetectorConstruction.hh"\nG4VPhysicalVolume* DetectorConstruction::Construct() { return nullptr; }',  # noqa: E501
                    },
                ],
            ),
        }

        gate_results = _make_gate_results_pass(["material", "geometry"])

        patch = assemble_proposed_patch(module_results, gate_results, "test_job")

        # Validate against PatchValidator
        pv = PatchValidator()
        valid, errors = pv.validate_patch_format(patch)
        assert valid, f"Patch validation failed: {errors}"

    def test_patch_has_required_top_level_fields(self, workspace: Path) -> None:
        """Patch must contain all required top-level fields."""
        module_results = {
            "material": _make_module_result(  # noqa: E501  # noqa: E501
                "material",
                [
                    {
                        "path": "src/MaterialRegistry.cc",
                        "new_content": "int x = 1;",
                    },
                ],
            ),
        }
        gate_results = _make_gate_results_pass(["material"])

        patch = assemble_proposed_patch(module_results, gate_results, "test_job")

        required_fields = [
            "patch_id",
            "job_id",
            "description",
            "change_type",
            "risk_level",
            "changed_files",
            "test_plan",
            "expected_outputs",
        ]
        for field in required_fields:
            assert field in patch, f"Missing required field: {field}"

    def test_patch_id_includes_job_id(self, workspace: Path) -> None:
        """patch_id should contain the job_id."""
        module_results = {
            "material": _make_module_result(
                "material",
                [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            ),
        }
        gate_results = _make_gate_results_pass(["material"])

        patch = assemble_proposed_patch(module_results, gate_results, "my_job_42")

        assert "my_job_42" in patch["patch_id"]
        assert patch["job_id"] == "my_job_42"

    def test_change_type_is_valid(self, workspace: Path) -> None:
        """change_type should be a recognized value."""
        module_results = {
            "material": _make_module_result(
                "material",
                [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            ),
        }
        gate_results = _make_gate_results_pass(["material"])

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        valid_types = {"create", "modify", "create_or_replace"}
        assert patch["change_type"] in valid_types

    def test_risk_level_is_valid(self, workspace: Path) -> None:
        """risk_level should be a recognized value."""
        module_results = {
            "material": _make_module_result(
                "material",
                [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            ),
        }
        gate_results = _make_gate_results_pass(["material"])

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        valid_levels = {"low", "medium", "high", "critical"}
        assert patch["risk_level"] in valid_levels

    def test_changed_files_not_empty_when_modules_pass(self, workspace: Path) -> None:
        """changed_files should not be empty when at least one module passes."""
        module_results = {
            "material": _make_module_result(
                "material",
                [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            ),
        }
        gate_results = _make_gate_results_pass(["material"])

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        assert len(patch["changed_files"]) > 0

    def test_two_modules_both_pass(self, workspace: Path) -> None:
        """Both modules pass both gates — all files should be in patch."""
        module_results = {
            "material": _make_module_result(
                "material",
                [
                    {"path": "src/Material.cc", "new_content": "// material"},
                ],
            ),
            "physics": _make_module_result(
                "physics",
                [
                    {"path": "src/Physics.cc", "new_content": "// physics"},
                ],
            ),
        }
        gate_results = _make_gate_results_pass(["material", "physics"])

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        paths = [f["path"] for f in patch["changed_files"]]
        assert "src/Material.cc" in paths
        assert "src/Physics.cc" in paths

    def test_global_repair_lists_all_cmake_sources(self, workspace: Path) -> None:
        """Global repair should make CMakeLists.txt explicitly reference all src files."""
        module_results = {
            "main_cmake": _make_module_result(
                "main_cmake",
                [
                    {
                        "path": "CMakeLists.txt",
                        "new_content": (
                            "cmake_minimum_required(VERSION 3.16)\n"
                            "project(RadAgentG4)\n"
                            "find_package(Geant4 REQUIRED)\n"
                            "file(GLOB SOURCES \"src/*.cc\" \"main.cc\")\n"
                            "add_executable(RadAgentG4 ${SOURCES})\n"
                            "target_link_libraries(RadAgentG4 ${Geant4_LIBRARIES})\n"
                        ),
                    },
                    {"path": "main.cc", "new_content": "int main() { return 0; }\n"},
                ],
            ),
            "material": _make_module_result(
                "material",
                [{"path": "src/MaterialRegistry.cc", "new_content": "// material\n"}],
            ),
            "geometry": _make_module_result(
                "geometry",
                [{"path": "src/DetectorConstruction.cc", "new_content": "// geometry\n"}],
            ),
        }
        gate_results = _make_gate_results_pass(["main_cmake", "material", "geometry"])

        patch = assemble_proposed_patch(module_results, gate_results, "test")
        patch, report = run_global_code_repair(patch, "test")

        cmake = next(f for f in patch["changed_files"] if f["path"] == "CMakeLists.txt")
        assert "src/MaterialRegistry.cc" in cmake["new_content"]
        assert "src/DetectorConstruction.cc" in cmake["new_content"]
        assert "CMAKE_CXX_STANDARD 17" in cmake["new_content"]
        assert report["status"] == "passed"
        assert any(i["target"] == "CMakeLists.txt" for i in report["issues_fixed"])

    def test_global_repair_adds_output_manager_write_event(self, workspace: Path) -> None:
        """Global repair should add the OutputManager WriteEvent adapter."""
        patch = {
            "changed_files": [
                {
                    "path": "CMakeLists.txt",
                    "new_content": (
                        "cmake_minimum_required(VERSION 3.16)\n"
                        "project(RadAgentG4)\n"
                        "find_package(Geant4 REQUIRED)\n"
                        "add_executable(RadAgentG4 main.cc)\n"
                    ),
                },
                {"path": "main.cc", "new_content": "int main() { return 0; }\n"},
                {
                    "path": "src/OutputManager.cc",
                    "new_content": "void OutputManager::EndEvent(const G4Event*) {}\n",
                },
                {
                    "path": "include/OutputManager.hh",
                    "new_content": (
                        "class OutputManager {\n"
                        "public:\n"
                        "    void EndEvent(const G4Event* anEvent);\n"
                        "};\n"
                    ),
                },
            ]
        }

        repaired, report = run_global_code_repair(patch, "test")

        header = next(
            f for f in repaired["changed_files"] if f["path"] == "include/OutputManager.hh"
        )
        source = next(f for f in repaired["changed_files"] if f["path"] == "src/OutputManager.cc")
        assert "WriteEvent(const G4Event* anEvent)" in header["new_content"]
        assert "OutputManager::WriteEvent(" in source["new_content"]
        assert report["status"] == "passed"
