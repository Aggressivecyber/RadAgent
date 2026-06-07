"""E2E test — module gate failure blocks patch generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_core.g4_codegen.integration.integration_assembler import assemble_proposed_patch
from agent_core.models.gateway import reset_model_gateway


@pytest.fixture(autouse=True)
def _reset_gw() -> None:
    reset_model_gateway()
    yield
    reset_model_gateway()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestG4CodegenModuleGateFailureBlocksPatch:
    """Verify that a module gate failure prevents files from that module appearing in patch."""

    def test_failed_module_files_not_in_patch(self, workspace: Path) -> None:
        """Files from a failed module should not appear in the assembled patch."""
        module_results = {
            "material": {
                "module_name": "material",
                "status": "generated",
                "generated_files": [
                    {
                        "path": "src/Mat.cc",
                        "operation": "create_or_replace",
                        "new_content": "// material code",
                        "generated_by": "material_module_agent",
                        "module_name": "material",
                        "rationale": "",
                        "dependencies": [],
                        "satisfies": [],
                        "risk_notes": [],
                        "used_references": [],
                    },
                ],
                "errors": [],
                "warnings": [],
            },
            "geometry": {
                "module_name": "geometry",
                "status": "generated",
                "generated_files": [
                    {
                        "path": "src/Det.cc",
                        "operation": "create_or_replace",
                        "new_content": "// geometry code",
                        "generated_by": "geometry_module_agent",
                        "module_name": "geometry",
                        "rationale": "",
                        "dependencies": [],
                        "satisfies": [],
                        "risk_notes": [],
                        "used_references": [],
                    },
                ],
                "errors": [],
                "warnings": [],
            },
        }

        # Material passes, geometry fails
        gate_results = {
            "material": {
                "hard": {"status": "pass"},
                "llm": {"status": "pass"},
            },
            "geometry": {
                "hard": {"status": "fail", "errors": ["empty include"]},
                "llm": {"status": "skipped"},
            },
        }

        patch = assemble_proposed_patch(module_results, gate_results, "gate_fail_test")

        # Only material files should be in patch
        paths = [f["path"] for f in patch["changed_files"]]
        assert "src/Mat.cc" in paths
        assert "src/Det.cc" not in paths, "Failed module files should not be in patch"

    def test_all_modules_fail_produces_empty_patch(self, workspace: Path) -> None:
        """If all modules fail gates, patch should have no changed_files."""
        module_results = {
            "material": {
                "module_name": "material",
                "status": "generated",
                "generated_files": [
                    {
                        "path": "src/Mat.cc",
                        "new_content": "// mat",
                        "operation": "create_or_replace",
                        "generated_by": "material_module_agent",
                        "module_name": "material",
                        "rationale": "",
                        "dependencies": [],
                        "satisfies": [],
                        "risk_notes": [],
                        "used_references": [],
                    },
                ],
                "errors": [],
                "warnings": [],
            },
        }

        gate_results = {
            "material": {
                "hard": {"status": "fail"},
                "llm": {"status": "skipped"},
            },
        }

        patch = assemble_proposed_patch(module_results, gate_results, "all_fail_test")

        assert len(patch["changed_files"]) == 0
