"""Tests for Patch Subgraph."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from agent_core.patching.nodes import apply_patch, load_proposed_patch, review_patch


@pytest.fixture
def temp_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))
    return workspace


class TestLoadProposedPatch:
    async def test_loads_from_file(self, temp_workspace: Path) -> None:
        patch_file = temp_workspace / "patch.json"
        patch_file.write_text(
            json.dumps({"changed_files": [{"path": "test.cc", "content": "int main(){}"}]})
        )

        state = {"proposed_patch_path": str(patch_file)}
        result = await load_proposed_patch(state)
        assert result["proposed_patch"]["changed_files"][0]["path"] == "test.cc"

    async def test_missing_file_returns_empty(self) -> None:
        state = {"proposed_patch_path": "/nonexistent/patch.json"}
        result = await load_proposed_patch(state)
        assert result["proposed_patch"] == {}


class TestReviewPatch:
    async def test_valid_patch_passes(self, temp_workspace: Path) -> None:
        job_dir = temp_workspace / "jobs" / "test" / "09_validation"
        job_dir.mkdir(parents=True)

        from agent_core.validators.file_permission_validator import FilePermissionValidator

        state = {
            "job_id": "test",
            "proposed_patch": {
                "patch_id": "p1",
                "job_id": "test",
                "description": "test patch",
                "change_type": "modify",
                "risk_level": "low",
                "changed_files": [
                    {"path": "src/main.cc", "new_content": "// test", "zone": "green"},
                ],
                "test_plan": "compile",
                "expected_outputs": {},
            },
        }

        with patch.object(FilePermissionValidator, "__init__", lambda self, **kw: None):
            with patch.object(
                FilePermissionValidator,
                "validate_patch_permissions",
                return_value=(True, ["All green zone"]),
            ):
                result = await review_patch(state)

        assert result["patch_review_result"]["format_valid"] is True

    async def test_rejects_path_traversal(self, temp_workspace: Path) -> None:
        job_dir = temp_workspace / "jobs" / "test" / "09_validation"
        job_dir.mkdir(parents=True)

        from agent_core.validators.file_permission_validator import FilePermissionValidator

        state = {
            "job_id": "test",
            "proposed_patch": {
                "patch_id": "p2",
                "job_id": "test",
                "description": "bad patch",
                "change_type": "modify",
                "risk_level": "critical",
                "changed_files": [
                    {"path": "../../../etc/passwd", "new_content": "bad", "zone": "red"},
                ],
                "test_plan": "none",
                "expected_outputs": {},
            },
        }

        with patch.object(FilePermissionValidator, "__init__", lambda self, **kw: None):
            with patch.object(
                FilePermissionValidator,
                "validate_patch_permissions",
                return_value=(False, ["red zone: ../../../etc/passwd"]),
            ):
                result = await review_patch(state)

        assert not result["patch_review_result"]["permission_valid"]


class TestApplyPatch:
    async def test_applies_files(self, temp_workspace: Path) -> None:
        code_dir = temp_workspace / "code"
        code_dir.mkdir()
        val_dir = temp_workspace / "jobs" / "test" / "09_validation"
        val_dir.mkdir(parents=True)

        state = {
            "job_id": "test",
            "generated_code_dir": str(code_dir),
            "proposed_patch": {
                "changed_files": [
                    {
                        "path": "src/main.cc",
                        "content": "#include <iostream>\nint main() { return 0; }",
                    },
                ],
            },
            "patch_review_result": {"errors": []},
            "errors": [],
        }
        result = await apply_patch(state)
        assert result["patch_status"] == "applied"
        assert (code_dir / "src" / "main.cc").exists()
        assert result["patch_applied_at"] != ""

    async def test_rejects_review_errors(self, temp_workspace: Path) -> None:
        state = {
            "job_id": "test",
            "generated_code_dir": "/tmp/test",
            "proposed_patch": {},
            "patch_review_result": {"errors": ["format invalid"]},
            "errors": [],
        }
        result = await apply_patch(state)
        assert result["patch_status"] == "rejected"
