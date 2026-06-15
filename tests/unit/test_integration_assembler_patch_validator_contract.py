"""Test that assemble_proposed_patch output satisfies PatchValidator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
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


class TestAssembleProposedPatchPatchValidatorContract:
    """Verify that assemble_proposed_patch output passes PatchValidator."""

    def test_patch_satisfies_validator(self, workspace: Path) -> None:
        """assemble_proposed_patch output must satisfy PatchValidator."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {
                        "path": "src/MaterialRegistry.cc",
                        "new_content": '#include "MaterialRegistry.hh"\nvoid MaterialRegistry::DefineMaterials() {}',  # noqa: E501
                    },
                ],
            ),
            "beam_physics": _make_module_result(
                "beam_physics",
                [
                    {
                        "path": "src/PrimaryGeneratorAction.cc",
                        "new_content": '#include "PrimaryGeneratorAction.hh"\nvoid PrimaryGeneratorAction::GeneratePrimaries(G4Event*) {}',  # noqa: E501
                    },
                ],
            ),
        }

        patch = assemble_proposed_patch(module_results, "test_job")

        # Validate against PatchValidator
        pv = PatchValidator()
        valid, errors = pv.validate_patch_format(patch)
        assert valid, f"Patch validation failed: {errors}"

    def test_patch_has_required_top_level_fields(self, workspace: Path) -> None:
        """Patch must contain all required top-level fields."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {
                        "path": "src/MaterialRegistry.cc",
                        "new_content": "int x = 1;",
                    },
                ],
            ),
        }

        patch = assemble_proposed_patch(module_results, "test_job")

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

    def test_patch_includes_failed_module_files_for_global_repair(
        self,
        workspace: Path,
    ) -> None:
        """Failed modules with files must not be discarded before repair."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {
                        "path": "src/DetectorConstruction.cc",
                        "new_content": '#include "DetectorConstruction.hh"\n#include "Bad.hh"\n',
                    },
                ],
                status="failed",
            )
        }

        patch = assemble_proposed_patch(module_results, "test_job")
        paths = {entry["path"] for entry in patch["changed_files"]}

        assert "src/DetectorConstruction.cc" in paths
        assert patch["metadata"]["failed_module_count"] == 1
        assert patch["metadata"]["repair_input_module_count"] == 1

    def test_patch_metadata_reports_obvious_cross_module_method_mismatch(
        self,
        workspace: Path,
    ) -> None:
        """Assembler should surface API mismatches before global repair spends turns."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {
                        "path": "include/PlacementManager.hh",
                        "new_content": (
                            "#pragma once\n"
                            "class G4VPhysicalVolume;\n"
                            "class PlacementManager {\n"
                            "public:\n"
                            "  G4VPhysicalVolume* GetPhysicalVolume(const char* id) const;\n"
                            "};\n"
                        ),
                    },
                    {
                        "path": "src/DetectorConstruction.cc",
                        "new_content": (
                            '#include "PlacementManager.hh"\n'
                            "void Build(PlacementManager* fPlacementManager) {\n"
                            '  fPlacementManager->RegisterPhysicalVolume("world", nullptr);\n'
                            "}\n"
                        ),
                    },
                ],
            )
        }

        patch = assemble_proposed_patch(module_results, "test_job")
        audit = patch["metadata"]["interface_audit"]

        assert audit["status"] == "fail"
        assert any(
            issue["kind"] == "unknown_method"
            and issue["class_name"] == "PlacementManager"
            and issue["method"] == "RegisterPhysicalVolume"
            and issue["path"] == "src/DetectorConstruction.cc"
            for issue in audit["issues"]
        )
        assert any("RegisterPhysicalVolume" in item for item in audit["repair_hints"])

    def test_patch_metadata_reports_constructor_arity_mismatch(
        self,
        workspace: Path,
    ) -> None:
        module_results = {
            "runtime_app": _make_module_result(
                "runtime_app",
                [
                    {
                        "path": "include/ActionInitialization.hh",
                        "new_content": (
                            "#pragma once\n"
                            "class OutputManager;\n"
                            "class ActionInitialization {\n"
                            "public:\n"
                            "  explicit ActionInitialization(OutputManager* outputManager);\n"
                            "};\n"
                        ),
                    },
                    {
                        "path": "main.cc",
                        "new_content": (
                            '#include "ActionInitialization.hh"\n'
                            "int main() {\n"
                            "  auto* action = new ActionInitialization();\n"
                            "  return action == nullptr;\n"
                            "}\n"
                        ),
                    },
                ],
            )
        }

        patch = assemble_proposed_patch(module_results, "test_job")
        audit = patch["metadata"]["interface_audit"]

        assert audit["status"] == "fail"
        assert any(
            issue["kind"] == "constructor_arity_mismatch"
            and issue["class_name"] == "ActionInitialization"
            and issue["actual_arg_count"] == 0
            and 1 in issue["allowed_arg_counts"]
            for issue in audit["issues"]
        )

    def test_patch_id_includes_job_id(self, workspace: Path) -> None:
        """patch_id should contain the job_id."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            ),
        }

        patch = assemble_proposed_patch(module_results, "my_job_42")

        assert "my_job_42" in patch["patch_id"]
        assert patch["job_id"] == "my_job_42"

    def test_change_type_is_valid(self, workspace: Path) -> None:
        """change_type should be a recognized value."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            ),
        }

        patch = assemble_proposed_patch(module_results, "test")

        valid_types = {"create", "modify", "create_or_replace"}
        assert patch["change_type"] in valid_types

    def test_risk_level_is_valid(self, workspace: Path) -> None:
        """risk_level should be a recognized value."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            ),
        }

        patch = assemble_proposed_patch(module_results, "test")

        valid_levels = {"low", "medium", "high", "critical"}
        assert patch["risk_level"] in valid_levels

    def test_changed_files_not_empty_when_modules_pass(self, workspace: Path) -> None:
        """changed_files should not be empty when at least one module passes."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {"path": "src/test.cc", "new_content": "// test"},
                ],
            ),
        }

        patch = assemble_proposed_patch(module_results, "test")

        assert len(patch["changed_files"]) > 0

    def test_two_modules_both_pass(self, workspace: Path) -> None:
        """Generated/repaired modules should forward all files into the patch."""
        module_results = {
            "simulation_core": _make_module_result(
                "simulation_core",
                [
                    {"path": "src/Material.cc", "new_content": "// material"},
                ],
            ),
            "beam_physics": _make_module_result(
                "beam_physics",
                [
                    {"path": "src/Physics.cc", "new_content": "// physics"},
                ],
            ),
        }

        patch = assemble_proposed_patch(module_results, "test")

        paths = [f["path"] for f in patch["changed_files"]]
        assert "src/Material.cc" in paths
        assert "src/Physics.cc" in paths
