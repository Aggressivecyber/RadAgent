"""Tests for Artifact Subgraph — rich manifest and correct field names.

Verifies:
  - geometry_interface_report uses correct schema field names
  - artifact_manifest.json is rich: sha256, size_bytes, source_commit, schema_version
  - review_report.json is rich: is_stub, generated_at, schema_version
  - Empty state still produces valid manifest
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_core.artifacts.nodes import (
    collect_artifacts,
    generate_artifact_manifest,
)


class TestGeometryInterfaceReportFields:
    """Verify geometry_interface_report uses correct schema field names."""

    async def test_uses_component_a_not_parent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        # Create model IR with interfaces using correct schema
        ir_dir = tmp_path / "jobs" / "test" / "03_model_ir"
        ir_dir.mkdir(parents=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(
            json.dumps(
                {
                    "interfaces": [
                        {
                            "interface_id": "world_sensor",
                            "component_a": "world",
                            "component_b": "sensor",
                            "relationship": "contains",
                            "overlap_check_enabled": True,
                        },
                    ],
                }
            )
        )

        state = {
            "job_id": "test",
            "g4_model_ir_path": str(ir_path),
            "errors": [],
        }
        result = await collect_artifacts(state)
        artifact_dir = Path(result["review_artifact_dir"])
        gi_path = artifact_dir / "output" / "geometry_interface_report.json"

        if gi_path.exists():
            gi_report = json.loads(gi_path.read_text())
            iface = gi_report["interfaces"][0]
            # Must use correct field names from GeometryInterfaceSpec
            assert "component_a" in iface, "Must use component_a (not parent_component)"
            assert "component_b" in iface, "Must use component_b (not child_component)"
            assert "relationship" in iface, "Must use relationship (not interface_type)"
            assert iface["component_a"] == "world"
            assert iface["component_b"] == "sensor"
            assert iface["relationship"] == "contains"

    async def test_no_parent_component_field(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Must NOT contain old wrong field names."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        ir_dir = tmp_path / "jobs" / "test2" / "03_model_ir"
        ir_dir.mkdir(parents=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(
            json.dumps(
                {
                    "interfaces": [
                        {
                            "interface_id": "a_b",
                            "component_a": "a",
                            "component_b": "b",
                            "relationship": "contains",
                        },
                    ],
                }
            )
        )

        state = {
            "job_id": "test2",
            "g4_model_ir_path": str(ir_path),
            "errors": [],
        }
        result = await collect_artifacts(state)
        gi_path = Path(result["review_artifact_dir"]) / "output" / "geometry_interface_report.json"

        if gi_path.exists():
            gi_report = json.loads(gi_path.read_text())
            report_text = json.dumps(gi_report)
            assert "parent_component" not in report_text
            assert "child_component" not in report_text
            assert "interface_type" not in report_text


class TestRichManifest:
    """Verify artifact_manifest.json has rich metadata."""

    async def test_manifest_has_sha256_and_size(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        # Create model IR so collect_artifacts produces some output files
        ir_dir = tmp_path / "jobs" / "test3" / "03_model_ir"
        ir_dir.mkdir(parents=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(
            json.dumps(
                {
                    "components": [{"component_id": "world"}],
                    "materials": [],
                    "sources": [],
                    "scoring": [],
                    "interfaces": [],
                    "simplification_policy": {"allow_simplification": False},
                }
            )
        )

        state = {
            "job_id": "test3",
            "g4_model_ir_path": str(ir_path),
            "validation_status": "PARTIAL",
            "errors": [],
        }
        collect_result = await collect_artifacts(state)
        manifest_result = await generate_artifact_manifest(
            {
                **state,
                **collect_result,
            }
        )

        manifest_path = Path(manifest_result["artifact_manifest_path"])
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())

        # Rich manifest fields
        assert manifest["schema_version"] == "v3"
        assert "generated_at" in manifest
        assert "source_commit" in manifest
        assert manifest["total_files"] > 0

        # Each file entry must have sha256 and size_bytes
        for entry in manifest["files"]:
            assert "name" in entry
            assert "sha256" in entry
            assert "size_bytes" in entry
            assert len(entry["sha256"]) == 64, f"SHA256 must be 64 chars: {entry}"

    async def test_review_report_is_rich(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        ir_dir = tmp_path / "jobs" / "test4" / "03_model_ir"
        ir_dir.mkdir(parents=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(
            json.dumps(
                {
                    "components": [{"component_id": "world"}],
                    "materials": [],
                    "sources": [],
                    "scoring": [],
                }
            )
        )

        state = {
            "job_id": "test4",
            "g4_model_ir_path": str(ir_path),
            "validation_status": "PARTIAL",
            "errors": [],
        }
        collect_result = await collect_artifacts(state)
        await generate_artifact_manifest({**state, **collect_result})

        artifact_dir = Path(collect_result["review_artifact_dir"])
        review_path = artifact_dir / "review_report.json"
        assert review_path.exists()

        review = json.loads(review_path.read_text())
        assert review["schema_version"] == "v3"
        assert review["is_stub"] is False
        assert "generated_at" in review
        assert review["validation_status"] == "PARTIAL"
        assert review["artifacts_collected"] > 0

    async def test_empty_state_produces_manifest(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Even with no input files, manifest should be valid and have schema_version."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        state = {
            "job_id": "empty_test",
            "validation_status": "UNKNOWN",
            "errors": [],
        }
        collect_result = await collect_artifacts(state)
        manifest_result = await generate_artifact_manifest(
            {
                **state,
                **collect_result,
            }
        )

        manifest_path = Path(manifest_result["artifact_manifest_path"])
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        # Rich manifest must always have these fields
        assert manifest["schema_version"] == "v3"
        assert "generated_at" in manifest
        assert "source_commit" in manifest
        assert "files" in manifest
        assert isinstance(manifest["files"], list)


class TestDevModeValidationStatus:
    """Verify dev mode forces validation_status to PARTIAL (never VERIFIED)."""

    async def test_dev_mode_downgrades_verified_to_partial(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dev mode with VERIFIED input must downgrade to PARTIAL."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        ir_dir = tmp_path / "jobs" / "dev_test" / "03_model_ir"
        ir_dir.mkdir(parents=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(
            json.dumps(
                {
                    "components": [
                        {
                            "component_id": "world",
                            "component_type": "world",
                            "geometry_type": "box",
                        },
                        {
                            "component_id": "target",
                            "component_type": "volume",
                            "geometry_type": "cylinder",
                        },
                    ],
                    "materials": ["G4_AIR"],
                    "sources": [],
                    "scoring": [],
                }
            )
        )

        state = {
            "job_id": "dev_test",
            "execution_mode": "dev",  # Dev mode
            "validation_status": "VERIFIED",  # Should be downgraded
            "g4_model_ir_path": str(ir_path),
            "gate_results": [],
            "errors": [],
        }
        collect_result = await collect_artifacts(state)
        manifest_result = await generate_artifact_manifest(
            {
                **state,
                **collect_result,
            }
        )

        manifest_path = Path(manifest_result["artifact_manifest_path"])
        manifest = json.loads(manifest_path.read_text())

        # Must be PARTIAL, not VERIFIED
        assert manifest["validation_status"] == "PARTIAL", (
            f"Dev mode must downgrade VERIFIED to PARTIAL, got {manifest['validation_status']}"
        )
        assert manifest["run_type"] == "dev"

        # Known limitations should mention dev mode downgrade
        limitations = " ".join(manifest.get("known_limitations", []))
        assert "dev mode" in limitations.lower(), (
            f"Known limitations should mention dev mode downgrade: {limitations}"
        )

    async def test_acceptance_mode_preserves_verified(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Acceptance mode should preserve VERIFIED status."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        ir_dir = tmp_path / "jobs" / "acc_test" / "03_model_ir"
        ir_dir.mkdir(parents=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(
            json.dumps(
                {
                    "components": [{"component_id": "world"}],
                    "materials": [],
                    "sources": [],
                    "scoring": [],
                }
            )
        )

        state = {
            "job_id": "acc_test",
            "execution_mode": "acceptance",  # Acceptance mode
            "validation_status": "VERIFIED",  # Should be preserved
            "g4_model_ir_path": str(ir_path),
            "gate_results": [],
            "errors": [],
        }
        collect_result = await collect_artifacts(state)
        manifest_result = await generate_artifact_manifest(
            {
                **state,
                **collect_result,
            }
        )

        manifest_path = Path(manifest_result["artifact_manifest_path"])
        manifest = json.loads(manifest_path.read_text())

        # Acceptance mode preserves VERIFIED
        assert manifest["validation_status"] == "VERIFIED"
        assert manifest["run_type"] == "acceptance"

    async def test_dev_mode_with_partial_stays_partial(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Dev mode with PARTIAL input should stay PARTIAL."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        state = {
            "job_id": "dev_partial",
            "execution_mode": "dev",
            "validation_status": "PARTIAL",  # Already PARTIAL
            "errors": [],
        }
        collect_result = await collect_artifacts(state)
        manifest_result = await generate_artifact_manifest(
            {
                **state,
                **collect_result,
            }
        )

        manifest_path = Path(manifest_result["artifact_manifest_path"])
        manifest = json.loads(manifest_path.read_text())

        assert manifest["validation_status"] == "PARTIAL"
        assert manifest["run_type"] == "dev"


class TestModelIRSummaryExtraction:
    """Verify model_ir_summary is extracted from g4_model_ir, not hardcoded."""

    async def test_model_ir_summary_components_from_g4_model_ir(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """model_ir_summary.components must match g4_model_ir components."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))

        # Create a complex model with 9 components
        expected_components = [
            {"component_id": "world", "component_type": "world", "geometry_type": "box"},
            {"component_id": "target", "component_type": "volume", "geometry_type": "cylinder"},
            {"component_id": "shield_1", "component_type": "volume", "geometry_type": "box"},
            {"component_id": "shield_2", "component_type": "volume", "geometry_type": "box"},
            {"component_id": "detector_1", "component_type": "volume", "geometry_type": "box"},
            {"component_id": "detector_2", "component_type": "volume", "geometry_type": "box"},
            {"component_id": "detector_3", "component_type": "volume", "geometry_type": "box"},
            {"component_id": "collimator", "component_type": "volume", "geometry_type": "tube"},
            {"component_id": "housing", "component_type": "volume", "geometry_type": "box"},
        ]

        ir_dir = tmp_path / "jobs" / "complex_test" / "03_model_ir"
        ir_dir.mkdir(parents=True)
        ir_path = ir_dir / "g4_model_ir.json"
        ir_path.write_text(
            json.dumps(
                {
                    "components": expected_components,
                    "materials": ["G4_AIR", "G4_Si", "G4_Pb"],
                    "sources": ["gps_source"],
                    "scoring": ["dose_scoring", "energy_deposit"],
                }
            )
        )

        state = {
            "job_id": "complex_test",
            "execution_mode": "dev",
            "validation_status": "PARTIAL",
            "g4_model_ir_path": str(ir_path),
            "gate_results": [],
            "errors": [],
        }
        collect_result = await collect_artifacts(state)
        manifest_result = await generate_artifact_manifest(
            {
                **state,
                **collect_result,
            }
        )

        manifest_path = Path(manifest_result["artifact_manifest_path"])
        manifest = json.loads(manifest_path.read_text())

        # Verify model_ir_summary matches g4_model_ir
        summary = manifest["model_ir_summary"]
        assert len(summary["components"]) == 9, (
            f"Expected 9 components, got {len(summary['components'])}"
        )
        assert summary["materials_count"] == 3
        assert summary["scoring_count"] == 2

        # Verify component IDs match
        component_ids = [c["component_id"] for c in summary["components"]]
        expected_ids = [c["component_id"] for c in expected_components]
        assert component_ids == expected_ids, (
            f"Component IDs mismatch: expected {expected_ids}, got {component_ids}"
        )
