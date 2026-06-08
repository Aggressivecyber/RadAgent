"""Tests that artifact collection includes human confirmation files."""

import json
from pathlib import Path

import pytest
from agent_core.artifacts.nodes import collect_artifacts, generate_artifact_manifest


@pytest.fixture
def artifact_state_with_confirmation(tmp_path, monkeypatch):
    """Create artifact state with human confirmation files."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    job_id = "hc_test"
    from agent_core.config.workspace import ensure_job_dirs

    job_dir = ensure_job_dirs(job_id)

    # Create model IR
    ir_dir = job_dir / "03_model_ir"
    ir_dir.mkdir(parents=True, exist_ok=True)
    ir = {"components": [{"component_id": "world"}], "materials": [], "sources": [], "scoring": []}
    (ir_dir / "g4_model_ir.json").write_text(json.dumps(ir))

    # Create human confirmation files
    hc_dir = job_dir / "04_human_confirmation"
    hc_dir.mkdir(parents=True, exist_ok=True)
    (hc_dir / "confirmation_record.json").write_text(
        json.dumps(
            {
                "final_status": "approved",
                "remaining_unconfirmed_fields": [],
            }
        )
    )
    (hc_dir / "confirmed_model_plan.json").write_text(
        json.dumps(
            {
                "confirmation_status": "approved",
            }
        )
    )
    (hc_dir / "human_confirmation_report.md").write_text("# Report\n")

    # Create gate results
    val_dir = job_dir / "09_validation"
    val_dir.mkdir(parents=True, exist_ok=True)
    gates = [{"gate_id": i, "status": "pass", "checked_items": []} for i in range(20)]
    (val_dir / "gate_results.json").write_text(json.dumps(gates))

    return {
        "job_id": job_id,
        "gate_results_path": str(val_dir / "gate_results.json"),
        "g4_model_ir_path": str(ir_dir / "g4_model_ir.json"),
        "model_review_report_path": "",
        "construction_ledger_path": "",
        "code_module_plan_path": "",
        "proposed_patch_path": "",
        "validation_status": "PARTIAL",
        "errors": [],
    }


@pytest.mark.asyncio
async def test_artifact_collects_confirmation_record(artifact_state_with_confirmation):
    result = await collect_artifacts(artifact_state_with_confirmation)
    output_dir = Path(result["review_artifact_dir"]) / "output"
    assert (output_dir / "confirmation_record.json").exists()


@pytest.mark.asyncio
async def test_artifact_collects_confirmed_model_plan(artifact_state_with_confirmation):
    result = await collect_artifacts(artifact_state_with_confirmation)
    output_dir = Path(result["review_artifact_dir"]) / "output"
    assert (output_dir / "confirmed_model_plan.json").exists()


@pytest.mark.asyncio
async def test_artifact_collects_confirmation_report(artifact_state_with_confirmation):
    result = await collect_artifacts(artifact_state_with_confirmation)
    output_dir = Path(result["review_artifact_dir"]) / "output"
    assert (output_dir / "human_confirmation_report.md").exists()


@pytest.mark.asyncio
async def test_review_report_shows_human_confirmation(artifact_state_with_confirmation):
    result = await collect_artifacts(artifact_state_with_confirmation)
    artifact_state_with_confirmation.update(result)
    await generate_artifact_manifest(artifact_state_with_confirmation)
    review = json.loads((Path(result["review_artifact_dir"]) / "review_report.json").read_text())
    assert review["has_human_confirmation"] is True
