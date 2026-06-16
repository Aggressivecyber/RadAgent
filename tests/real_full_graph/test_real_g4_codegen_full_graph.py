from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from agent_core.gates import build_gate_validation_subgraph
from agent_core.graph.subgraphs.g4_codegen_graph import build_g4_codegen_subgraph
from agent_core.patching.nodes import apply_patch
from agent_core.workspace.paths import STAGE_GATE_VALIDATION, STAGE_INPUT

from tests.fixtures.real_g4_case import build_real_g4_model_ir, require_real_model_api


async def test_real_g4_codegen_full_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    require_real_model_api()
    workspace = tmp_path / "simulation_workspace"
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(workspace))

    job_id = "real_full_graph"
    job_dir = workspace / "jobs" / job_id
    input_dir = job_dir / STAGE_INPUT
    input_dir.mkdir(parents=True)

    g4_model_ir_path = input_dir / "g4_model_ir.json"
    g4_model_ir_path.write_text(
        json.dumps(build_real_g4_model_ir(job_id), indent=2),
        encoding="utf-8",
    )
    task_spec_path = input_dir / "task_spec.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "simulation_scope": ["geant4"],
                "particle": {
                    "type": "proton",
                    "energy_MeV": 10.0,
                    "direction": [0.0, 0.0, 1.0],
                    "events": 1000,
                },
                "target": {
                    "material": "Silicon",
                    "size_um": [20000.0, 20000.0, 500.0],
                    "geometry_type": "box",
                },
                "outputs": ["edep", "dose"],
                "physics_options": {"physics_list": "FTFP_BERT"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    confirmation_record_path = input_dir / "confirmation_record.json"
    confirmed_model_plan_path = input_dir / "confirmed_model_plan.json"
    confirmation_record_path.write_text(
        json.dumps(
            {
                "schema_version": "confirmation_record_v1",
                "job_id": job_id,
                "final_status": "approved",
                "remaining_unconfirmed_fields": [],
                "confirmed_model_plan_path": str(confirmed_model_plan_path),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    confirmed_model_plan_path.write_text(
        json.dumps(
            {
                "schema_version": "confirmed_model_plan_v1",
                "confirmation_status": "approved",
                "remaining_unconfirmed_fields": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    graph = build_g4_codegen_subgraph().compile()
    result = await graph.ainvoke(
        {
            "job_id": job_id,
            "run_mode": "strict",
            "execution_mode": "real",
            "g4_model_ir_path": str(g4_model_ir_path),
            "codegen_errors": [],
            "codegen_warnings": [],
        }
    )

    assert result["g4_codegen_status"] == "passed"
    assert result["proposed_patch"]
    assert result["proposed_patch"]["changed_files"]
    assert result["global_integration_agent_report"]["status"] == "passed"
    assert result["physics_quality_review"]["status"] == "pass"
    assert result["proposed_patch"]["metadata"]["final_runtime_gate"]["required"] is True
    assert result["generated_code_dir"].endswith("geant4_project")

    required_modules = {
        "simulation_core",
        "beam_physics",
        "runtime_app",
    }
    modules_in_patch = {f["module_name"] for f in result["proposed_patch"]["changed_files"]}
    assert required_modules.issubset(modules_in_patch)

    for file_entry in result["proposed_patch"]["changed_files"]:
        assert "new_content" in file_entry
        assert "content" not in file_entry
        assert "zone" in file_entry
        assert "generated_by" in file_entry
        assert "module_name" in file_entry
        assert file_entry["path"]
        assert not file_entry["path"].startswith("geant4_project/")

    patch_result = await apply_patch(
        {
            "job_id": job_id,
            "proposed_patch": result["proposed_patch"],
            "generated_code_dir": result["generated_code_dir"],
            "errors": [],
        }
    )
    assert patch_result["patch_status"] == "applied"

    g4_dir = Path(result["generated_code_dir"])
    assert (g4_dir / "CMakeLists.txt").exists()
    assert (g4_dir / "main.cc").exists()
    assert (g4_dir / "src").exists()
    assert (g4_dir / "include").exists()
    assert any((g4_dir / "src").glob("*.cc"))
    assert any((g4_dir / "include").glob("*.hh"))

    gate_graph = build_gate_validation_subgraph().compile()
    gate_result = await gate_graph.ainvoke(
        {
            "job_id": job_id,
            "run_mode": "strict",
            "execution_mode": "strict",
            "g4_model_ir_path": str(g4_model_ir_path),
            "task_spec_path": str(task_spec_path),
            "generated_code_dir": result["generated_code_dir"],
            "applied_patch_path": patch_result["applied_patch_path"],
            "patch_applied_at": patch_result["patch_applied_at"],
            "context_decision": "allow_rag",
            "confirmation_status": "approved",
            "confirmation_record_path": str(confirmation_record_path),
            "confirmed_model_plan_path": str(confirmed_model_plan_path),
            "unconfirmed_assumptions_count": 0,
            "visual_review_status": "approved",
            "visual_review_notes": (
                "100-event visual workbench artifacts reviewed: geometry, "
                "particle tracks, and energy deposits are present."
            ),
            "retry_count": 0,
        }
    )
    assert gate_result["validation_status"] == "passed"

    output_dir = job_dir / STAGE_GATE_VALIDATION / "g4_output_package"
    geometry = json.loads((output_dir / "geometry_view.json").read_text(encoding="utf-8"))
    tracks = json.loads((output_dir / "particle_tracks.json").read_text(encoding="utf-8"))
    deposits = json.loads((output_dir / "energy_deposits.json").read_text(encoding="utf-8"))
    assert geometry["components"]
    assert tracks["tracks"]
    assert deposits["deposits"]

    artifact_check = subprocess.run(
        [
            sys.executable,
            "scripts/acceptance_check_artifacts.py",
            "--artifact-dir",
            str(job_dir),
        ],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )
    assert artifact_check.returncode == 0, artifact_check.stdout + artifact_check.stderr
