"""E2E test — full pipeline from workspace prep to review artifacts.

This test verifies the complete data flow through the main graph:
  prepare_workspace → context → task_planning → g4_modeling →
  g4_codegen → patch → gates → artifact → report

Key verifications:
1. All job directories are created
2. Review artifacts are collected in review_artifacts/g4_complex_model/latest/
3. Final report is generated
4. Artifact manifest lists all expected files
5. No simplification report is correct
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from agent_core.artifacts.nodes import (
    collect_artifacts,
    generate_artifact_manifest,
    generate_artifact_readme,
)
from agent_core.config.workspace import ensure_job_dirs, get_job_dir
from agent_core.graph.main_graph import prepare_workspace
from agent_core.patching.nodes import apply_patch
from agent_core.reports.nodes import generate_final_report

# ─── Helpers ──────────────────────────────────────────────────────────


def _create_model_ir(job_dir: Path) -> Path:
    """Create a minimal but valid G4ModelIR for E2E testing."""
    ir_dir = job_dir / "03_model_ir"
    ir_dir.mkdir(parents=True, exist_ok=True)
    ir_path = ir_dir / "g4_model_ir.json"

    model_ir = {
        "model_ir_id": "e2e_test_mir",
        "job_id": "e2e_test",
        "modeling_mode": "realistic",
        "target_system": "E2E Test Detector",
        "simplification_policy": {
            "allow_simplification": False,
            "requires_user_approval": True,
            "approved_simplifications": [],
        },
        "components": [
            {
                "component_id": "world",
                "display_name": "World Volume",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 5000, "dy": 5000, "dz": 5000},
                "material_id": "G4_AIR",
                "roles": [],
                "open_issues": [],
                "source_evidence": ["default"],
            },
            {
                "component_id": "silicon_detector",
                "display_name": "Silicon Detector",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 100, "dy": 100, "dz": 50},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "roles": ["edep_region"],
                "open_issues": [],
                "source_evidence": ["user_specification"],
            },
        ],
        "materials": [
            {
                "material_id": "G4_AIR",
                "name": "G4_AIR",
                "classification": "nist",
                "nist_name": "G4_AIR",
                "density_g_cm3": 0.001214,
                "custom": False,
                "source_evidence": ["NIST"],
            },
            {
                "material_id": "G4_Si",
                "name": "G4_Si",
                "classification": "nist",
                "nist_name": "G4_Si",
                "density_g_cm3": 2.329,
                "custom": False,
                "source_evidence": ["NIST"],
            },
        ],
        "sources": [
            {
                "source_id": "proton_beam",
                "particle_type": "proton",
                "energy": {"value": 100.0, "unit": "MeV", "distribution": "mono"},
                "beam": {
                    "position": [0, 0, 5000],
                    "direction": [0, 0, -1],
                    "surface_shape": "point",
                },
                "generator_type": "gun",
                "source_evidence": ["user_specification"],
            },
        ],
        "physics": {
            "physics_list": "FTFP_BERT",
            "selection_reasoning": "FTFP_BERT covers proton therapy range with EM + hadronic.",
            "source_evidence": ["standard_physics"],
        },
        "scoring": [
            {
                "scoring_id": "edep_silicon",
                "scoring_type": "region",
                "quantities": ["edep_MeV"],
                "target_component_id": "silicon_detector",
                "output_format": "csv",
                "source_evidence": ["user_specification"],
            },
        ],
        "interfaces": [
            {
                "parent_component": "world",
                "child_component": "silicon_detector",
                "interface_type": "daughter",
            },
        ],
        "open_issues": [],
        "evidence": {
            "evidence_decision": "allow_rag",
            "geometry": ["user_specification: silicon box"],
            "materials": ["NIST: G4_AIR", "NIST: G4_Si"],
            "source": ["user_specification: 100 MeV proton"],
            "physics": ["standard_physics: FTFP_BERT"],
            "scoring": ["user_specification: edep in silicon"],
        },
        "ledger": {
            "entries": [],
            "version": "1.0",
        },
    }

    ir_path.write_text(json.dumps(model_ir, indent=2, ensure_ascii=False))
    return ir_path


def _create_gate_results(job_dir: Path) -> Path:
    """Create gate results file."""
    val_dir = job_dir / "09_validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    gate_path = val_dir / "gate_results.json"

    gates = []
    for gid in range(12):
        gates.append({
            "gate_id": gid,
            "gate_name": f"Gate {gid}",
            "severity": "pass",
            "message": "OK",
        })
    for gid in range(12, 19):
        gates.append({
            "gate_id": gid,
            "gate_name": f"G4-{chr(65 + gid - 12)}",
            "severity": "pass",
            "message": "OK",
        })

    gate_path.write_text(json.dumps(gates, indent=2))
    return gate_path


def _create_patch(job_dir: Path) -> Path:
    """Create a valid proposed patch."""
    val_dir = job_dir / "09_validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    patch_path = val_dir / "proposed_patch.json"

    patch = {
        "patch_id": "e2e_patch",
        "job_id": "e2e_test",
        "description": "E2E test patch",
        "change_type": "modify",
        "risk_level": "low",
        "changed_files": [
            {
                "path": "src/DetectorConstruction.cc",
                "new_content": '#include "DetectorConstruction.hh"\n// E2E test content\n',
                "zone": "green",
            },
        ],
        "test_plan": "compile",
        "expected_outputs": {"exit_code": 0},
    }

    patch_path.write_text(json.dumps(patch, indent=2))
    return patch_path


def _create_code_dir(job_dir: Path) -> Path:
    """Create generated code directory with a file."""
    code_dir = job_dir / "04_codegen" / "output"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "src").mkdir(exist_ok=True)
    (code_dir / "src" / "DetectorConstruction.cc").write_text("// placeholder\n")
    return code_dir


# ─── E2E Test ─────────────────────────────────────────────────────────


class TestE2EPipeline:
    """End-to-end pipeline test with mocked LLM/RAG calls."""

    async def test_full_pipeline_generates_review_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full pipeline: workspace → context → planning → modeling →
        codegen → patch → gates → artifacts → report.

        Verifies review_artifacts/ contains all expected files.
        """
        # Setup workspace
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

        job_id = "e2e_test"

        # Step 1: Prepare workspace
        state: dict[str, Any] = {
            "job_id": job_id,
            "user_query": "Simulate 100 MeV proton beam hitting silicon detector",
            "execution_mode": "dev_no_geant4_env",
        }
        result = await prepare_workspace(state)
        assert result["job_id"] == job_id

        job_dir = get_job_dir(job_id)
        assert (job_dir / "00_request").exists()
        assert (job_dir / "00_request" / "user_query.md").exists()

        # Step 2: Simulate context subgraph output
        state.update(result)
        state["context_decision"] = "allow_rag"
        state["context_report_path"] = str(job_dir / "01_context" / "report.json")
        state["evidence_map_path"] = str(job_dir / "01_context" / "evidence_map.json")

        context_dir = job_dir / "01_context"
        context_dir.mkdir(parents=True, exist_ok=True)
        (context_dir / "report.json").write_text(json.dumps({"decision": "allow_rag"}))
        (context_dir / "evidence_map.json").write_text(json.dumps({"geant4": []}))

        # Step 3: Simulate task planning output
        state["task_planning_status"] = "passed"
        state["simulation_scope"] = ["geant4"]
        task_spec_path = job_dir / "02_task_spec" / "task_spec.json"
        task_spec_path.parent.mkdir(parents=True, exist_ok=True)
        task_spec_path.write_text(json.dumps({
            "particle": "proton",
            "energy_MeV": 100,
            "scope": ["geant4"],
        }))
        state["task_spec_path"] = str(task_spec_path)

        # Step 4: G4 Modeling — create model IR
        ir_path = _create_model_ir(job_dir)
        state["g4_model_ir_path"] = str(ir_path)
        state["g4_modeling_status"] = "passed"
        state["component_specs_dir"] = str(job_dir / "03_model_ir" / "component_specs")
        state["interfaces_path"] = str(job_dir / "03_model_ir" / "interfaces.json")
        state["construction_ledger_path"] = str(
            job_dir / "03_model_ir" / "construction_ledger.json"
        )
        state["model_review_report_path"] = str(
            job_dir / "03_model_ir" / "model_review_report.md"
        )

        # Create supporting files
        comp_dir = job_dir / "03_model_ir" / "component_specs"
        comp_dir.mkdir(parents=True, exist_ok=True)
        (comp_dir / "world.json").write_text(json.dumps({"component_id": "world"}))
        (comp_dir / "silicon_detector.json").write_text(
            json.dumps({"component_id": "silicon_detector"})
        )
        (job_dir / "03_model_ir" / "interfaces.json").write_text(
            json.dumps([{"parent": "world", "child": "silicon_detector"}])
        )
        (job_dir / "03_model_ir" / "construction_ledger.json").write_text(
            json.dumps({"entries": [], "version": "1.0"})
        )
        (job_dir / "03_model_ir" / "model_review_report.md").write_text(
            "# Model Review\n\nAll components verified.\n"
        )

        # Step 5: G4 Codegen — create code and patch
        code_dir = _create_code_dir(job_dir)
        state["generated_code_dir"] = str(code_dir)
        state["g4_codegen_status"] = "passed"
        patch_path = _create_patch(job_dir)
        state["proposed_patch_path"] = str(patch_path)
        state["code_module_plan_path"] = str(
            job_dir / "04_codegen" / "code_module_plan.json"
        )
        (job_dir / "04_codegen" / "code_module_plan.json").write_text(
            json.dumps({"modules": ["DetectorConstruction"]})
        )

        # Step 6: Patch — apply the patch
        from agent_core.validators.file_permission_validator import FilePermissionValidator

        with patch.object(FilePermissionValidator, "__init__", lambda self, **kw: None):
            with patch.object(
                FilePermissionValidator,
                "validate_patch_permissions",
                return_value=(True, ["All green zone"]),
            ):
                patch_state = {
                    "job_id": job_id,
                    "proposed_patch_path": str(patch_path),
                    "generated_code_dir": str(code_dir),
                }

                from agent_core.patching.nodes import (
                    load_proposed_patch,
                    review_patch,
                )

                loaded = await load_proposed_patch(patch_state)
                patch_state.update(loaded)
                reviewed = await review_patch(patch_state)
                patch_state.update(reviewed)
                applied = await apply_patch(patch_state)
                assert applied["patch_status"] == "applied"

        state["patch_status"] = "applied"
        state["applied_patch_path"] = applied.get("applied_patch_path", "")
        state["patch_applied_at"] = applied.get("patch_applied_at", "")

        # Step 7: Gates — create gate results
        gate_path = _create_gate_results(job_dir)
        state["gate_results_path"] = str(gate_path)
        state["validation_status"] = "VERIFIED"
        state["failed_gates"] = []
        state["skipped_gates"] = []

        # Step 8: Artifact collection
        artifact_state: dict[str, Any] = {
            "job_id": job_id,
            "gate_results_path": str(gate_path),
            "g4_model_ir_path": str(ir_path),
            "model_review_report_path": state["model_review_report_path"],
            "construction_ledger_path": state["construction_ledger_path"],
            "code_module_plan_path": state["code_module_plan_path"],
            "proposed_patch_path": str(patch_path),
            "validation_status": "VERIFIED",
            "errors": [],
        }
        collected = await collect_artifacts(artifact_state)
        assert collected.get("artifact_status") != "failed"

        artifact_state.update(collected)
        manifest = await generate_artifact_manifest(artifact_state)
        assert manifest["artifact_status"] == "collected"

        artifact_state.update(manifest)
        await generate_artifact_readme(artifact_state)

        # Verify review artifacts
        artifact_dir = Path(collected["review_artifact_dir"])
        assert artifact_dir.exists()
        assert (artifact_dir / "README.md").exists()
        assert (artifact_dir / "artifact_manifest.json").exists()
        assert (artifact_dir / "review_report.json").exists()
        assert (artifact_dir / "output").exists()

        # Verify specific output files
        output_dir = artifact_dir / "output"
        assert (output_dir / "g4_model_ir.json").exists()
        assert (output_dir / "gate_results.json").exists()
        assert (output_dir / "component_specs_summary.json").exists()
        assert (output_dir / "no_simplification_report.json").exists()
        assert (output_dir / "geometry_interface_report.json").exists()
        assert (output_dir / "evidence_traceability_report.json").exists()

        # Verify no_simplification report content
        no_simp = json.loads((output_dir / "no_simplification_report.json").read_text())
        assert no_simp["allow_simplification"] is False
        assert no_simp["status"] == "NO_SIMPLIFICATION"

        # Verify component summary
        comp_summary = json.loads(
            (output_dir / "component_specs_summary.json").read_text()
        )
        assert comp_summary["total_components"] == 2
        assert "world" in comp_summary["component_ids"]
        assert "silicon_detector" in comp_summary["component_ids"]
        assert comp_summary["materials_count"] == 2

        # Verify artifact manifest
        manifest_data = json.loads(
            (artifact_dir / "artifact_manifest.json").read_text()
        )
        # Dev mode: validation_status is downgraded from VERIFIED to PARTIAL
        assert manifest_data["validation_status"] != "VERIFIED"
        assert manifest_data["total_files"] >= 6

        # Verify review_report.json
        review_report = json.loads(
            (artifact_dir / "review_report.json").read_text()
        )
        assert review_report["has_model_ir"] is True
        assert review_report["has_gate_results"] is True

        # Step 9: Generate final report
        report_state: dict[str, Any] = {
            "job_id": job_id,
            "user_query": "Simulate 100 MeV proton beam hitting silicon detector",
            "execution_mode": "dev_no_geant4_env",
            "validation_status": "VERIFIED",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4"],
            "failed_gates": [],
            "errors": [],
            "g4_model_ir_path": str(ir_path),
            "gate_results_path": str(gate_path),
        }
        report_result = await generate_final_report(report_state)
        assert report_result["verified"] is True
        assert report_result["termination_reason"] == "completed_verified"

        report_path = Path(report_result["final_report_path"])
        assert report_path.exists()

        report_text = report_path.read_text()
        assert "PARTIAL" in report_text or "VERIFIED" in report_text
        assert "silicon_detector" in report_text
        assert "proton" in report_text
        assert "Allow simplification" in report_text
        assert "`False`" in report_text
        assert "e2e_test" in report_text

    async def test_pipeline_blocked_no_context(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If context is blocked, pipeline goes directly to report."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

        job_id = "blocked_test"

        state: dict[str, Any] = {
            "job_id": job_id,
            "user_query": "Unclear request with no simulation details",
            "execution_mode": "dev_no_geant4_env",
            "context_decision": "block_no_context",
            "simulation_scope": [],
            "failed_gates": [],
            "errors": ["Insufficient context"],
            "g4_model_ir_path": "",
            "gate_results_path": "",
        }

        report_result = await generate_final_report(state)
        assert report_result["verified"] is False
        assert "blocked_no_context" == report_result["termination_reason"]

    async def test_artifact_archive_on_rerun(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Re-running artifact collection should produce consistent output."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

        job_id = "rerun_test"
        job_dir = ensure_job_dirs(job_id)
        ir_path = _create_model_ir(job_dir)
        gate_path = _create_gate_results(job_dir)

        artifact_state: dict[str, Any] = {
            "job_id": job_id,
            "gate_results_path": str(gate_path),
            "g4_model_ir_path": str(ir_path),
            "model_review_report_path": "",
            "construction_ledger_path": "",
            "code_module_plan_path": "",
            "proposed_patch_path": "",
            "validation_status": "VERIFIED",
            "errors": [],
        }

        # First run
        result1 = await collect_artifacts(artifact_state)
        artifact_dir = Path(result1["review_artifact_dir"])
        output_dir = artifact_dir / "output"
        files_run1 = sorted(f.name for f in output_dir.iterdir() if f.is_file())

        # Second run (same data)
        await collect_artifacts(artifact_state)
        files_run2 = sorted(f.name for f in output_dir.iterdir() if f.is_file())

        # Same files both times
        assert files_run1 == files_run2
        assert len(files_run1) >= 4
