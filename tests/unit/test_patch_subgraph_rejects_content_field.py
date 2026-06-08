"""Test that apply_patch rejects 'content' field and only accepts 'new_content'."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.patching.nodes import apply_patch


class TestPatchSubgraphRejectsContentField:
    """Verify apply_patch handles content vs new_content correctly."""

    @pytest.mark.asyncio
    async def test_rejects_content_without_new_content(self, tmp_path: Path) -> None:
        """apply_patch must reject entries with only 'content' (no 'new_content')."""
        code_dir = tmp_path / "08_geant4"
        code_dir.mkdir()

        state = {
            "job_id": "test",
            "proposed_patch": {
                "patch_id": "p1",
                "changed_files": [
                    {"path": "src/test.cc", "content": "// old-style content"},
                ],
            },
            "patch_review_result": {},
            "generated_code_dir": str(code_dir),
            "errors": [],
        }

        result = await apply_patch(state)

        # Should have errors about content field
        assert result["patch_status"] in ("failed", "rejected")
        has_content_error = any(
            "content" in e.lower() or "new_content" in e.lower() for e in result.get("errors", [])
        )
        assert has_content_error, f"Expected content-related error, got: {result.get('errors', [])}"

    @pytest.mark.asyncio
    async def test_rejects_both_content_and_new_content(self, tmp_path: Path) -> None:
        """P0-8/P0-9: apply_patch must reject entries with both 'content' AND 'new_content'."""
        code_dir = tmp_path / "08_geant4"
        code_dir.mkdir()

        state = {
            "job_id": "test",
            "proposed_patch": {
                "patch_id": "p1",
                "changed_files": [
                    {
                        "path": "src/test.cc",
                        "content": "old",
                        "new_content": "// new",
                    },
                ],
            },
            "patch_review_result": {},
            "generated_code_dir": str(code_dir),
            "errors": [],
        }

        result = await apply_patch(state)

        # P0-8: Any 'content' field is forbidden, even with new_content present
        assert result["patch_status"] in ("failed", "rejected"), (
            f"Expected failed/rejected, got: {result['patch_status']}"
        )
        has_content_error = any("content" in e.lower() for e in result.get("errors", []))
        assert has_content_error, f"Expected content-related error, got: {result.get('errors', [])}"
        # File must NOT have been written
        written_file = code_dir / "src" / "test.cc"
        assert not written_file.exists(), (
            f"File should not be written when content field is present: {written_file}"
        )

    @pytest.mark.asyncio
    async def test_accepts_only_new_content(self, tmp_path: Path) -> None:
        """apply_patch must accept entries with only 'new_content'."""
        code_dir = tmp_path / "08_geant4"
        code_dir.mkdir()

        state = {
            "job_id": "test",
            "proposed_patch": {
                "patch_id": "p1",
                "changed_files": [
                    {
                        "path": "src/test.cc",
                        "new_content": "// valid content",
                    },
                ],
            },
            "patch_review_result": {},
            "generated_code_dir": str(code_dir),
            "errors": [],
        }

        result = await apply_patch(state)

        assert result["patch_status"] == "applied"
        # File should have been written
        written_file = code_dir / "src" / "test.cc"
        assert written_file.exists()
        assert written_file.read_text() == "// valid content"
