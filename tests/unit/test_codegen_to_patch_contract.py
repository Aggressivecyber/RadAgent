"""Tests for Codegen → Patch contract consistency.

Verifies:
- integration_assembler_node outputs changed_files with new_content
- patching apply_patch reads new_content (with deprecated content fallback)
- PatchValidator validates the new format
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agent_core.validators.patch_validator import PatchValidator


def _make_minimal_model_ir_dict() -> dict[str, Any]:
    """Create a minimal valid g4_model_ir dict for testing."""
    return {
        "model_ir_id": "test_v1",
        "job_id": "test_job",
        "target_system": "Test Detector",
        "components": [
            {
                "component_id": "world",
                "display_name": "World",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 100.0, "dy": 100.0, "dz": 100.0},
                "material_id": "G4_AIR",
                "source_evidence": ["test"],
            }
        ],
        "materials": [
            {
                "material_id": "G4_AIR",
                "name": "G4_AIR",
                "classification": "nist",
                "nist_name": "G4_AIR",
                "density_g_cm3": 0.001214,
                "source_evidence": ["NIST"],
            }
        ],
        "sources": [
            {
                "source_id": "proton",
                "particle_type": "proton",
                "energy": {"value": 10.0, "unit": "MeV"},
                "beam": {"position": [0, 0, 0], "direction": [0, 0, -1]},
                "source_evidence": ["test"],
            }
        ],
        "physics": {
            "physics_list": "QGSP_BIC_HP",
            "selection_reasoning": "QGSP_BIC_HP for standard proton simulation",
            "source_evidence": ["test"],
        },
        "scoring": [
            {
                "scoring_id": "edep",
                "scoring_type": "region",
                "quantities": ["edep_MeV"],
                "region_scores": [{"region_component_id": "world", "quantity": "edep_MeV"}],
                "source_evidence": ["test"],
            }
        ],
    }


class TestCodegenPatchContract:
    """Verify codegen output matches patch input schema."""

    @pytest.mark.asyncio
    async def test_assembler_outputs_changed_files_with_new_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """integration_assembler_node must output changed_files[].new_content."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        from agent_core.g4_modeling.nodes.integration_assembler_node import (
            integration_assembler_node,
        )

        state = {
            "code_modules": [
                {
                    "module_name": "TestModule",
                    "module_type": "detector",
                    "source_files": ["TestModule.cc"],
                    "header_files": ["TestModule.hh"],
                    "config_files": [],
                    "generated_content": {
                        "TestModule::TestModule.cc": "// C++ source",
                        "TestModule::TestModule.hh": "// C++ header",
                    },
                }
            ],
            "g4_model_ir": _make_minimal_model_ir_dict(),
            "job_id": "test_job",
        }

        result = await integration_assembler_node(state)
        patch = result["code_patch"]

        # Must use new schema
        assert patch["patch_type"] == "json_file_replacement"
        assert "changed_files" in patch
        assert len(patch["changed_files"]) == 2

        # Each file must have new_content, not content
        for f in patch["changed_files"]:
            assert "path" in f
            assert "new_content" in f
            assert f["new_content"], f"new_content empty for {f['path']}"
            assert "content" not in f, f"Old 'content' field found for {f['path']}"
            assert f.get("operation") == "create_or_replace"
            assert f.get("zone") == "green"

    def test_patch_validator_accepts_new_format(self) -> None:
        """PatchValidator must accept changed_files with new_content."""
        patch = {
            "patch_id": "test_patch",
            "job_id": "test",
            "description": "test patch",
            "change_type": "create",
            "risk_level": "low",
            "changed_files": [
                {
                    "path": "src/test.cc",
                    "new_content": "// test",
                    "zone": "green",
                }
            ],
            "test_plan": ["compile"],
            "expected_outputs": [],
        }

        pv = PatchValidator()
        valid, errors = pv.validate_patch_format(patch)
        assert valid, f"Patch rejected: {errors}"

    def test_patch_validator_rejects_missing_new_content(self) -> None:
        """PatchValidator must reject files without new_content."""
        patch = {
            "patch_id": "bad_patch",
            "job_id": "test",
            "description": "test",
            "change_type": "create",
            "risk_level": "low",
            "changed_files": [
                {
                    "path": "src/test.cc",
                    "zone": "green",
                    # new_content missing
                }
            ],
            "test_plan": [],
            "expected_outputs": [],
        }

        pv = PatchValidator()
        valid, errors = pv.validate_patch_format(patch)
        assert not valid
        assert any("new_content" in e for e in errors)

    @pytest.mark.asyncio
    async def test_apply_patch_reads_new_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """apply_patch must read new_content field."""
        from agent_core.patching.nodes import apply_patch

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        code_dir = tmp_path / "jobs" / "test_job" / "generated_code"
        code_dir.mkdir(parents=True)

        state = {
            "proposed_patch": {
                "changed_files": [
                    {
                        "path": "src/test.cc",
                        "operation": "create_or_replace",
                        "new_content": "// hello from new_content",
                        "zone": "green",
                    }
                ]
            },
            "patch_review_result": {"errors": []},
            "generated_code_dir": str(code_dir),
            "job_id": "test_job",
            "errors": [],
        }

        result = await apply_patch(state)
        assert result["patch_status"] == "applied"

        written = (code_dir / "src" / "test.cc").read_text()
        assert "hello from new_content" in written

    @pytest.mark.asyncio
    async def test_apply_patch_warns_on_deprecated_content(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """apply_patch must REJECT deprecated 'content' field (no longer supported)."""
        from agent_core.patching.nodes import apply_patch

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        code_dir = tmp_path / "jobs" / "test_job2" / "generated_code"
        code_dir.mkdir(parents=True)

        state = {
            "proposed_patch": {
                "changed_files": [
                    {
                        "path": "src/old.cc",
                        "content": "// old format",
                    }
                ]
            },
            "patch_review_result": {"errors": []},
            "generated_code_dir": str(code_dir),
            "job_id": "test_job2",
            "errors": [],
        }

        result = await apply_patch(state)
        # content-only entries should now be rejected (missing new_content)
        assert result["patch_status"] != "applied" or not (code_dir / "src" / "old.cc").exists()

    @pytest.mark.asyncio
    async def test_apply_patch_rejects_missing_both_fields(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """apply_patch must error when both new_content and content are missing."""
        from agent_core.patching.nodes import apply_patch

        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        code_dir = tmp_path / "jobs" / "test_job3" / "generated_code"
        code_dir.mkdir(parents=True)

        state = {
            "proposed_patch": {
                "changed_files": [
                    {
                        "path": "src/bad.cc",
                        # neither new_content nor content
                    }
                ]
            },
            "patch_review_result": {"errors": []},
            "generated_code_dir": str(code_dir),
            "job_id": "test_job3",
            "errors": [],
        }

        result = await apply_patch(state)
        assert result["patch_status"] == "failed"
        assert any("new_content" in e for e in result["errors"])
