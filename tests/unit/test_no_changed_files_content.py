"""Test that assemble_proposed_patch changed_files do not contain 'content' field."""

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


def _make_module_result(
    module_name: str,
    files: list[dict[str, str]],
) -> dict[str, Any]:
    generated_files = []
    for f in files:
        generated_files.append(
            {
                "path": f["path"],
                "operation": f.get("operation", "create_or_replace"),
                "new_content": f["new_content"],
                "generated_by": f.get("generated_by", f"{module_name}_module_agent"),
                "module_name": f.get("module_name", module_name),
                "rationale": f.get("rationale", ""),
                "dependencies": f.get("dependencies", []),
                "satisfies": f.get("satisfies", []),
                "risk_notes": f.get("risk_notes", []),
                "used_references": f.get("used_references", []),
            }
        )
    return {
        "module_name": module_name,
        "status": "generated",
        "generated_files": generated_files,
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


class TestNoChangedFilesContent:
    """Verify that changed_files in the assembled patch never use 'content'."""

    def test_no_content_field_in_changed_files(self, workspace: Path) -> None:
        """assemble_proposed_patch must not produce 'content' in changed_files."""
        module_results = {
            "material": _make_module_result(
                "material",
                [
                    {"path": "src/Mat.cc", "new_content": "// mat code"},
                ],
            ),
            "geometry": _make_module_result(
                "geometry",
                [
                    {"path": "src/Geom.cc", "new_content": "// geom code"},
                    {"path": "include/Geom.hh", "new_content": "#pragma once\n// geom header"},
                ],
            ),
        }
        gate_results = _gate_pass("material", "geometry")

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        for f in patch["changed_files"]:
            assert "content" not in f, (
                f"changed_files entry for {f['path']} contains 'content' field"
            )
            assert "new_content" in f, f"changed_files entry for {f['path']} missing 'new_content'"

    def test_only_new_content_is_present(self, workspace: Path) -> None:
        """Only new_content should be in changed_files (not content)."""
        module_results = {
            "physics": _make_module_result(
                "physics",
                [
                    {"path": "src/PhysicsList.cc", "new_content": "// physics"},
                ],
            ),
        }
        gate_results = _gate_pass("physics")

        patch = assemble_proposed_patch(module_results, gate_results, "test")

        for entry in patch["changed_files"]:
            keys = set(entry.keys())
            assert "new_content" in keys
            assert "content" not in keys
