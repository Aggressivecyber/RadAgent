"""Test that cross-file hard gate rejects 'content' field in generated_files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agent_core.g4_codegen.integration.cross_file_hard_gate import run_cross_file_hard_gate


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(ws))
    return ws


class TestHardGateRejectsContentField:
    """Verify cross-file hard gate rejects 'content' field in files."""

    def test_rejects_content_field(self, workspace: Path) -> None:
        """Files with 'content' field should fail cross-file hard gate."""
        proposed_patch = {
            "changed_files": [
                {
                    "path": "src/Test.cc",
                    "content": "// old-style content",
                    "new_content": "#include <iostream>\nint main() { return 0; }\n",
                },
            ],
        }

        result = run_cross_file_hard_gate(
            proposed_patch, {"classes": [], "file_structure": {}}, "test_content_field"
        )

        assert result["status"] == "fail"
        has_content_error = any(
            "content" in e.lower()
            for e in result.get("errors", [])
        )
        assert has_content_error, f"Expected 'content' rejection, errors: {result.get('errors', [])}"

    def test_passes_with_only_new_content(self, workspace: Path) -> None:
        """Files with only 'new_content' should not trigger content field error."""
        proposed_patch = {
            "changed_files": [
                {
                    "path": "src/Test.cc",
                    "new_content": "#include <iostream>\nint main() { return 0; }\n",
                },
            ],
        }

        result = run_cross_file_hard_gate(
            proposed_patch, {"classes": [], "file_structure": {}}, "test_new_content_only"
        )

        # Should not have a content-field-specific error
        content_errors = [
            e for e in result.get("errors", [])
            if "content" in e.lower() and "new_content" not in e.lower()
        ]
        assert len(content_errors) == 0, f"Unexpected content errors: {content_errors}"
