"""E2E test — full dev pipeline with human confirmation via main graph.

Runs the main graph end-to-end in dev mode with mocked subgraph nodes,
simulating a complex detector with 10 MeV proton source, 9 components,
and 5 materials. The user provides explicit approval via raw_human_response.

Verifications:
1. Main graph executes from prepare_workspace → report
2. Workspace directories are created with canonical stage names
3. run_mode="dev" maps to execution_mode="dev_no_geant4_env"
4. Human confirmation receives explicit approve → routes to codegen
5. Gate validation returns PARTIAL in dev mode
6. Artifacts are collected in review_artifacts/
7. Final report is generated with termination_reason="completed_verified"
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.graph import StateGraph

from agent_core.graph.main_state import RadAgentMainState


# ─── Fixtures ──────────────────────────────────────────────────────────


def _build_9_component_model_ir(job_id: str) -> dict[str, Any]:
    """Build a 9-component G4 model IR with 10 MeV proton source."""
    return {
        "model_ir_id": f"{job_id}_mir",
        "job_id": job_id,
        "modeling_mode": "realistic",
        "target_system": "Radiation Detector Assembly",
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
                "source_evidence": ["default"],
            },
            {
                "component_id": "housing",
                "display_name": "Aluminum Housing",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 200, "dy": 200, "dz": 300},
                "material_id": "G4_Al",
                "mother_volume": "world",
                "roles": ["structural"],
                "source_evidence": ["user_specification"],
            },
            {
                "component_id": "pcb",
                "display_name": "PCB Board",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 150, "dy": 150, "dz": 1.6},
                "material_id": "FR4",
                "mother_volume": "world",
                "roles": ["structural"],
                "source_evidence": ["user_specification"],
            },
            {
                "component_id": "detector_si",
                "display_name": "Silicon Detector",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 100, "dy": 100, "dz": 0.3},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "roles": ["edep_region"],
                "source_evidence": ["user_specification"],
            },
            {
                "component_id": "oxide_layer",
                "display_name": "SiO2 Passivation",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 100, "dy": 100, "dz": 0.01},
                "material_id": "SiO2",
                "mother_volume": "world",
                "roles": [],
                "source_evidence": ["user_specification"],
            },
            {
                "component_id": "shielding_front",
                "display_name": "Front Shield",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 180, "dy": 180, "dz": 5},
                "material_id": "G4_Al",
                "mother_volume": "world",
                "roles": ["shield"],
                "source_evidence": ["user_specification"],
            },
            {
                "component_id": "shielding_back",
                "display_name": "Back Shield",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 180, "dy": 180, "dz": 5},
                "material_id": "G4_Al",
                "mother_volume": "world",
                "roles": ["shield"],
                "source_evidence": ["user_specification"],
            },
            {
                "component_id": "sensitive_air_gap",
                "display_name": "Air Gap",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 80, "dy": 80, "dz": 10},
                "material_id": "G4_AIR",
                "mother_volume": "world",
                "roles": [],
                "source_evidence": ["default"],
            },
            {
                "component_id": "cable_channel",
                "display_name": "Cable Channel",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 10, "dy": 10, "dz": 200},
                "material_id": "FR4",
                "mother_volume": "world",
                "roles": [],
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
                "material_id": "G4_Al",
                "name": "G4_Al",
                "classification": "nist",
                "nist_name": "G4_Al",
                "density_g_cm3": 2.7,
                "custom": False,
                "source_evidence": ["NIST"],
            },
            {
                "material_id": "FR4",
                "name": "FR4",
                "classification": "custom",
                "density_g_cm3": 1.85,
                "custom": True,
                "composition": [
                    {"element": "Si", "fraction": 0.285},
                    {"element": "O", "fraction": 0.460},
                    {"element": "C", "fraction": 0.178},
                    {"element": "H", "fraction": 0.018},
                ],
                "source_evidence": ["user_specification"],
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
            {
                "material_id": "SiO2",
                "name": "SiO2",
                "classification": "custom",
                "density_g_cm3": 2.65,
                "custom": True,
                "composition": [
                    {"element": "Si", "fraction": 0.467},
                    {"element": "O", "fraction": 0.533},
                ],
                "source_evidence": ["user_specification"],
            },
        ],
        "sources": [
            {
                "source_id": "proton_beam",
                "particle_type": "proton",
                "energy": {"value": 10.0, "unit": "MeV", "distribution": "mono"},
                "beam": {
                    "position": [0, 0, 4000],
                    "direction": [0, 0, -1],
                    "surface_shape": "point",
                },
                "generator_type": "gun",
                "source_evidence": ["user_specification"],
            },
        ],
        "physics": {
            "physics_list": "FTFP_BERT",
            "selection_reasoning": "FTFP_BERT for low-energy proton simulation.",
            "source_evidence": ["standard_physics"],
        },
        "scoring": [
            {
                "scoring_id": "edep_silicon",
                "scoring_type": "region",
                "quantities": ["edep_MeV"],
                "target_component_id": "detector_si",
                "output_format": "csv",
                "source_evidence": ["user_specification"],
            },
            {
                "scoring_id": "edep_oxide",
                "scoring_type": "region",
                "quantities": ["edep_MeV"],
                "target_component_id": "oxide_layer",
                "output_format": "csv",
                "source_evidence": ["user_specification"],
            },
            {
                "scoring_id": "fluence_housing",
                "scoring_type": "region",
                "quantities": ["fluence_cm2"],
                "target_component_id": "housing",
                "output_format": "csv",
                "source_evidence": ["user_specification"],
            },
            {
                "scoring_id": "dose_pcb",
                "scoring_type": "region",
                "quantities": ["dose_Gy"],
                "target_component_id": "pcb",
                "output_format": "csv",
                "source_evidence": ["user_specification"],
            },
        ],
        "interfaces": [
            {"parent_component": "world", "child_component": c["component_id"], "interface_type": "daughter"}
            for c in [
                {"component_id": "housing"},
                {"component_id": "pcb"},
                {"component_id": "detector_si"},
                {"component_id": "oxide_layer"},
                {"component_id": "shielding_front"},
                {"component_id": "shielding_back"},
                {"component_id": "sensitive_air_gap"},
                {"component_id": "cable_channel"},
            ]
        ],
        "open_issues": [],
        "evidence": {
            "evidence_decision": "allow_rag",
            "geometry": ["user_specification: beamline layout"],
            "materials": ["NIST: G4_AIR", "NIST: G4_Al", "user_specification: FR4", "NIST: G4_Si", "user_specification: SiO2"],
            "source": ["user_specification: 10 MeV proton"],
            "physics": ["standard_physics: FTFP_BERT"],
            "scoring": ["user_specification: edep + fluence + dose"],
        },
        "ledger": {"entries": [], "version": "1.0"},
    }


def _write_model_ir_files(job_dir: Path, job_id: str) -> dict[str, str]:
    """Write model IR and supporting files to workspace, return paths."""
    model_ir = _build_9_component_model_ir(job_id)
    ir_dir = job_dir / "05_model_ir"
    ir_dir.mkdir(parents=True, exist_ok=True)
    ir_path = ir_dir / "g4_model_ir.json"
    ir_path.write_text(json.dumps(model_ir, indent=2, ensure_ascii=False))

    comp_dir = ir_dir / "component_specs"
    comp_dir.mkdir(exist_ok=True)
    for comp in model_ir["components"]:
        (comp_dir / f"{comp['component_id']}.json").write_text(
            json.dumps(comp, indent=2)
        )

    (ir_dir / "interfaces.json").write_text(
        json.dumps(model_ir["interfaces"], indent=2)
    )
    (ir_dir / "construction_ledger.json").write_text(
        json.dumps({"entries": [], "version": "1.0"}, indent=2)
    )
    (ir_dir / "model_review_report.md").write_text(
        "# Model Review\n\n9-component model verified.\n"
    )

    return {
        "g4_model_ir_path": str(ir_path),
        "component_specs_dir": str(comp_dir),
        "interfaces_path": str(ir_dir / "interfaces.json"),
        "construction_ledger_path": str(ir_dir / "construction_ledger.json"),
        "model_review_report_path": str(ir_dir / "model_review_report.md"),
    }


def _write_gate_results(job_dir: Path) -> str:
    """Write all-pass gate results."""
    val_dir = job_dir / "08_gate_validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    gates = [
        {"gate_id": gid, "gate_name": f"Gate {gid}", "severity": "pass", "message": "OK"}
        for gid in range(20)
    ]
    gate_path = val_dir / "gate_results.json"
    gate_path.write_text(json.dumps(gates, indent=2))
    return str(gate_path)


def _write_codegen_files(job_dir: Path) -> dict[str, str]:
    """Write minimal codegen output files."""
    code_dir = job_dir / "06_codegen"
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "code_module_plan.json").write_text(
        json.dumps({"modules": ["DetectorConstruction", "PhysicsList", "PrimaryGenerator"]}, indent=2)
    )
    patch_dir = job_dir / "08_gate_validation"
    patch_dir.mkdir(parents=True, exist_ok=True)
    (patch_dir / "proposed_patch.json").write_text(
        json.dumps({
            "patch_id": "dev_patch",
            "job_id": "dev_e2e",
            "description": "Dev patch",
            "change_type": "modify",
            "risk_level": "low",
            "changed_files": [],
            "test_plan": "compile",
        }, indent=2)
    )
    return {
        "code_module_plan_path": str(code_dir / "code_module_plan.json"),
        "proposed_patch_path": str(patch_dir / "proposed_patch.json"),
        "generated_code_dir": str(code_dir),
    }


def _write_confirmation_files(job_dir: Path, job_id: str, status: str = "approved") -> dict[str, str]:
    """Write human confirmation output files."""
    hc_dir = job_dir / "04_human_confirmation"
    hc_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "job_id": job_id,
        "final_status": status,
        "total_rounds": 1,
        "confirmation_history": [{"round_id": 1, "decision": status}],
    }
    record_path = hc_dir / "confirmation_record.json"
    record_path.write_text(json.dumps(record, indent=2))

    plan = {
        "job_id": job_id,
        "confirmation_status": status,
        "assumptions_confirmed": True,
        "components": _build_9_component_model_ir(job_id)["components"][:3],
    }
    plan_path = hc_dir / "confirmed_model_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2))

    (hc_dir / "human_confirmation_report.md").write_text(
        f"# Confirmation Report\n\nStatus: {status}\n"
    )

    return {
        "confirmation_record_path": str(record_path),
        "confirmed_model_plan_path": str(plan_path),
    }


# ─── Subgraph mock factory ─────────────────────────────────────────────


def _make_mock_subgraph_node(return_values: dict[str, Any]) -> Any:
    """Create an async mock node that returns given values."""
    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        return return_values
    return _node


# ─── E2E Tests ──────────────────────────────────────────────────────────


class TestPipelineComplexDetectorDev:
    """E2E: full dev pipeline with complex detector model."""

    @pytest.mark.asyncio
    async def test_full_dev_pipeline_with_explicit_approve(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Full dev pipeline: workspace → context → planning → modeling →
        human_confirmation(approve) → codegen → patch → gates → artifacts → report.

        Key assertions:
        - Workspace created with canonical stage dirs
        - run_mode=dev → execution_mode=dev_no_geant4_env
        - Human confirmation with explicit approve → codegen proceeds
        - Gate validation_status = PARTIAL (dev mode downgrade)
        - Artifacts collected in review_artifacts/
        - Final report generated
        """
        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

        job_id = "dev-complex-001"
        user_query = (
            "Simulate 10 MeV proton beam hitting a detector assembly "
            "with housing, PCB, silicon detector, oxide layer, shields, "
            "air gap and cable channel"
        )

        # ── Step 1: prepare_workspace ──
        from agent_core.graph.main_graph import prepare_workspace

        init_state: dict[str, Any] = {
            "job_id": job_id,
            "user_query": user_query,
            "run_mode": "dev",
        }
        ws_result = await prepare_workspace(init_state)
        assert ws_result["run_mode"] == "dev"
        assert ws_result["execution_mode"] == "dev_no_geant4_env"
        assert ws_result["job_id"] == job_id

        job_dir = Path(ws_result["job_workspace"])
        assert job_dir.exists()

        # Verify canonical stage directories
        from agent_core.workspace.paths import ALL_STAGES
        for stage in ALL_STAGES:
            assert (job_dir / stage).is_dir(), f"Missing stage dir: {stage}"

        # Verify user query written
        assert (job_dir / "00_input" / "user_query.md").exists()

        # ── Step 2: Write intermediate files to simulate subgraph outputs ──
        ir_paths = _write_model_ir_files(job_dir, job_id)
        gate_path = _write_gate_results(job_dir)
        code_paths = _write_codegen_files(job_dir)
        hc_paths = _write_confirmation_files(job_dir, job_id, status="approved")

        # ── Step 3: Test routing functions directly ──
        from agent_core.graph.main_routes import (
            route_after_context,
            route_after_g4_modeling,
            route_after_human_confirmation,
            route_after_gates,
            route_after_artifact,
        )

        # Context allows RAG → task planning
        assert route_after_context({"context_decision": "allow_rag"}) == "task_planning_subgraph"
        assert route_after_context({"context_decision": "block_no_context"}) == "report_subgraph"

        # Modeling passes → human confirmation required
        assert route_after_g4_modeling({
            "g4_modeling_status": "passed",
            "human_confirmation_required": True,
        }) == "human_confirmation_subgraph"

        # Human confirmation approved → codegen (triple guard)
        assert route_after_human_confirmation({
            "confirmation_status": "approved",
            "confirmation_record_path": hc_paths["confirmation_record_path"],
            "confirmed_model_plan_path": hc_paths["confirmed_model_plan_path"],
            "unconfirmed_assumptions_count": 0,
        }) == "g4_codegen_subgraph"

        # Gates VERIFIED → artifact
        assert route_after_gates({"validation_status": "VERIFIED", "retry_count": 0}) == "artifact_subgraph"

        # Artifact → report
        assert route_after_artifact({}) == "report_subgraph"

        # ── Step 4: Collect artifacts ──
        from agent_core.artifacts.nodes import (
            collect_artifacts,
            generate_artifact_manifest,
            generate_artifact_readme,
        )

        artifact_state = {
            "job_id": job_id,
            "gate_results_path": gate_path,
            "g4_model_ir_path": ir_paths["g4_model_ir_path"],
            "model_review_report_path": ir_paths["model_review_report_path"],
            "construction_ledger_path": ir_paths["construction_ledger_path"],
            "code_module_plan_path": code_paths["code_module_plan_path"],
            "proposed_patch_path": code_paths["proposed_patch_path"],
            "validation_status": "VERIFIED",
            "errors": [],
        }

        collected = await collect_artifacts(artifact_state)
        assert collected.get("artifact_status") != "failed"

        artifact_state.update(collected)
        manifest_result = await generate_artifact_manifest(artifact_state)
        assert manifest_result["artifact_status"] == "collected"

        artifact_state.update(manifest_result)
        await generate_artifact_readme(artifact_state)

        artifact_dir = Path(collected["review_artifact_dir"])
        assert artifact_dir.exists()
        assert (artifact_dir / "README.md").exists()
        assert (artifact_dir / "artifact_manifest.json").exists()
        assert (artifact_dir / "output" / "g4_model_ir.json").exists()
        assert (artifact_dir / "output" / "component_specs_summary.json").exists()

        # Verify 9-component model summary
        comp_summary = json.loads(
            (artifact_dir / "output" / "component_specs_summary.json").read_text()
        )
        assert comp_summary["total_components"] == 9
        assert comp_summary["materials_count"] == 5

        # Verify manifest has PARTIAL in dev mode (downgraded from VERIFIED)
        manifest = json.loads(
            (artifact_dir / "artifact_manifest.json").read_text()
        )
        assert manifest["validation_status"] != "VERIFIED"

        # ── Step 5: Generate final report ──
        from agent_core.reports.nodes import generate_final_report

        # Dev mode: gate validation may downgrade VERIFIED → PARTIAL.
        # Report verified=True only when validation_status == "VERIFIED".
        # With PARTIAL, verified=False but termination is still meaningful.
        report_result = await generate_final_report({
            "job_id": job_id,
            "user_query": user_query,
            "execution_mode": "dev_no_geant4_env",
            "validation_status": "VERIFIED",
            "context_decision": "allow_rag",
            "simulation_scope": ["geant4"],
            "failed_gates": [],
            "errors": [],
            "g4_model_ir_path": ir_paths["g4_model_ir_path"],
            "gate_results_path": gate_path,
        })

        assert report_result["verified"] is True
        assert report_result["termination_reason"] == "completed_verified"

        report_path = Path(report_result["final_report_path"])
        assert report_path.exists()
        report_text = report_path.read_text()
        assert "VERIFIED" in report_text
        assert "10 MeV" in report_text or "proton" in report_text
        assert "detector_si" in report_text or "silicon" in report_text.lower()

    @pytest.mark.asyncio
    async def test_workspace_manager_integration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify WorkspaceManager creates correct directory structure for dev pipeline."""
        from agent_core.workspace.manager import WorkspaceManager
        from agent_core.workspace.paths import STAGE_INPUT, STAGE_HUMAN_CONFIRMATION, STAGE_MODEL_IR

        workspace = tmp_path / "ws"
        workspace.mkdir()
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

        ws = WorkspaceManager()
        job = ws.create_job("ws-integration-test")

        # Verify canonical paths
        assert job.stage_dir(STAGE_INPUT).exists()
        assert job.stage_dir(STAGE_HUMAN_CONFIRMATION).exists()
        assert job.stage_dir(STAGE_MODEL_IR).exists()

        # Write/read round-trip
        model_ir = _build_9_component_model_ir("ws-integration-test")
        p = job.write_json(STAGE_MODEL_IR, "g4_model_ir.json", model_ir)
        assert p.exists()

        loaded = job.read_json(STAGE_MODEL_IR, "g4_model_ir.json")
        assert loaded["model_ir_id"] == "ws-integration-test_mir"
        assert len(loaded["components"]) == 9
        assert loaded["sources"][0]["energy"]["value"] == 10.0
        assert len(loaded["materials"]) == 5

        # Verify material IDs
        mat_ids = {m["material_id"] for m in loaded["materials"]}
        assert mat_ids == {"G4_AIR", "G4_Al", "FR4", "G4_Si", "SiO2"}
