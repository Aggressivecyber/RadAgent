"""Test that changed_files paths are relative to 08_geant4, not absolute or prefixed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agent_core.g4_codegen.integration.integration_assembler import assemble_proposed_patch


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


def _make_module_result(module_name: str, path: str, content: str = "// code") -> dict[str, Any]:
    return {
        "module_name": module_name,
        "status": "generated",
        "generated_files": [
            {
                "path": path,
                "operation": "create_or_replace",
                "new_content": content,
                "generated_by": f"{module_name}_module_agent",
                "module_name": module_name,
                "rationale": "",
                "dependencies": [],
                "satisfies": [],
                "risk_notes": [],
                "used_references": [],
            },
        ],
        "errors": [],
        "warnings": [],
    }


def _gate_pass(*names: str) -> dict[str, dict[str, Any]]:
    return {
        n: {
            "hard": {"status": "pass", "checks": [], "errors": []},
            "llm": {"status": "pass", "checks": [], "errors": []},
        }
        for n in names
    }


class TestPatchPathsAreRelativeTo08Geant4:
    """Verify paths in changed_files are clean and relative."""

    def test_path_not_prefixed_with_08_geant4(self, workspace: Path) -> None:
        """Paths should not start with '08_geant4/'."""
        module_results = {
            "material": _make_module_result("material", "08_geant4/src/Mat.cc"),
        }
        gate_results = _gate_pass("material")

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        for f in patch["changed_files"]:
            assert not f["path"].startswith("08_geant4/"), (
                f"Path {f['path']} should not start with 08_geant4/"
            )

    def test_path_not_absolute(self, workspace: Path) -> None:
        """Paths should not start with '/'."""
        module_results = {
            "material": _make_module_result("material", "/src/Mat.cc"),
        }
        gate_results = _gate_pass("material")

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        for f in patch["changed_files"]:
            assert not f["path"].startswith("/"), (
                f"Path {f['path']} should not start with /"
            )

    def test_path_not_contains_dotdot(self, workspace: Path) -> None:
        """Paths should not contain '..' traversal."""
        module_results = {
            "material": _make_module_result("material", "src/../etc/passwd"),
        }
        gate_results = _gate_pass("material")

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        for f in patch["changed_files"]:
            assert ".." not in f["path"], (
                f"Path {f['path']} contains '..' — possible traversal"
            )

    def test_clean_path_from_08_geant4_prefix(self, workspace: Path) -> None:
        """Paths with 08_geant4/ prefix should be cleaned."""
        module_results = {
            "geometry": _make_module_result("geometry", "08_geant4/src/Detector.cc"),
        }
        gate_results = _gate_pass("geometry")

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        paths = [f["path"] for f in patch["changed_files"]]
        assert "src/Detector.cc" in paths

    def test_already_clean_path(self, workspace: Path) -> None:
        """Already clean paths should pass through unchanged."""
        module_results = {
            "physics": _make_module_result("physics", "src/PhysicsList.cc"),
        }
        gate_results = _gate_pass("physics")

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        paths = [f["path"] for f in patch["changed_files"]]
        assert "src/PhysicsList.cc" in paths
