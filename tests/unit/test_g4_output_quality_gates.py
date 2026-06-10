from __future__ import annotations

import json
from pathlib import Path

import pytest
from agent_core.gates.base_gates import run_base_gates
from agent_core.workspace.paths import STAGE_GATE_VALIDATION


def _write_bad_smoke_outputs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "g4_summary.json").write_text(
        json.dumps({"job_id": "quality_gate", "events_requested": 10, "smoke_success": True}),
        encoding="utf-8",
    )
    (output_dir / "event_table.csv").write_text("EventID,edep_MeV,dose_Gy\n", encoding="utf-8")
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,0\n1,0,0,0\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0\n1,0,0,0\n",
        encoding="utf-8",
    )
    (output_dir / "provenance.json").write_text(
        json.dumps({"job_id": "quality_gate"}),
        encoding="utf-8",
    )
    (output_dir / "smoke_simulation_result.json").write_text(
        json.dumps(
            {
                "success": True,
                "errors": "parameter value (Phantom) is not listed in the candidate List.",
            }
        ),
        encoding="utf-8",
    )
    (output_dir / "unit_test_result.json").write_text(
        json.dumps({"success": True}),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_base_gates_reject_empty_zero_smoke_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    job_id = "quality_gate"
    output_dir = tmp_path / "jobs" / job_id / STAGE_GATE_VALIDATION / "g4_output_package"
    _write_bad_smoke_outputs(output_dir)

    result = await run_base_gates(
        {
            "job_id": job_id,
            "run_mode": "strict",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "no_code"),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }
    )

    gates = {gate["gate_id"]: gate for gate in result["gate_results"]}
    assert gates[8]["status"] == "fail"
    assert "event_table.csv has no event rows" in gates[8]["message"]
    assert gates[9]["status"] == "fail"
    assert "Smoke simulation stderr" in gates[9]["message"]
    assert gates[11]["status"] == "fail"
    assert any("edep_3d.csv has no non-zero" in item for item in gates[11]["failed_items"])


@pytest.mark.asyncio
async def test_base_gates_reject_non_numeric_physics_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    job_id = "quality_gate_non_numeric"
    output_dir = tmp_path / "jobs" / job_id / STAGE_GATE_VALIDATION / "g4_output_package"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "g4_summary.json").write_text(
        json.dumps({"job_id": job_id, "events_requested": 1, "smoke_success": True}),
        encoding="utf-8",
    )
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.0,0.01\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,bad\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n",
        encoding="utf-8",
    )
    (output_dir / "provenance.json").write_text(json.dumps({"job_id": job_id}), encoding="utf-8")

    result = await run_base_gates(
        {
            "job_id": job_id,
            "run_mode": "strict",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {},
            "generated_code_dir": str(tmp_path / "no_code"),
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }
    )

    gate11 = [gate for gate in result["gate_results"] if gate["gate_id"] == 11][0]
    assert gate11["status"] == "fail"
    assert any("edep_3d.csv row 0: non-numeric edep_MeV" in item for item in gate11["failed_items"])
