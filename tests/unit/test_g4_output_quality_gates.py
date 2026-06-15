from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from agent_core.gates.base_gates import run_base_gates
from agent_core.gates.visual_review_gate import run_visual_review_gate
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


@pytest.mark.asyncio
async def test_base_gates_run_ir_event_count_self_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    job_id = "quality_gate_ir_events"
    code_dir = tmp_path / "generated_code"
    (code_dir / "src").mkdir(parents=True)
    (code_dir / "include").mkdir()
    (code_dir / "CMakeLists.txt").write_text(
        "find_package(Geant4 REQUIRED ui_all vis_all)\nadd_executable(sim main.cc)\n",
        encoding="utf-8",
    )
    seen: dict[str, Any] = {}

    class FakeRunner:
        geant4_available = True

        async def smoke_test(
            self,
            project_dir: str,
            *,
            job_id: str = "unknown",
            output_dir: str | None = None,
            events: int = 10,
        ) -> dict[str, Any]:
            seen["events"] = events
            out = Path(str(output_dir))
            out.mkdir(parents=True, exist_ok=True)
            (out / "cmake_configure_result.json").write_text(
                json.dumps({"success": True}),
                encoding="utf-8",
            )
            (out / "build_result.json").write_text(
                json.dumps({"success": True, "executable_path": str(code_dir / "build" / "sim")}),
                encoding="utf-8",
            )
            (out / "unit_test_result.json").write_text(
                json.dumps({"success": True}),
                encoding="utf-8",
            )
            (out / "smoke_simulation_result.json").write_text(
                json.dumps({"success": True, "errors": ""}),
                encoding="utf-8",
            )
            (out / "g4_summary.json").write_text(
                json.dumps({"job_id": job_id, "events_requested": events}),
                encoding="utf-8",
            )
            (out / "provenance.json").write_text(json.dumps({"job_id": job_id}), encoding="utf-8")
            (out / "event_table.csv").write_text(
                "EventID,edep_MeV,dose_Gy\n"
                + "\n".join(f"{i},1.0,0.01" for i in range(events))
                + "\n",
                encoding="utf-8",
            )
            (out / "edep_3d.csv").write_text("x,y,z,edep_MeV\n0,0,0,1.0\n", encoding="utf-8")
            (out / "dose_3d.csv").write_text("x,y,z,dose_Gy\n0,0,0,0.01\n", encoding="utf-8")
            return {
                "success": True,
                "cmake_configure_result": {"success": True},
                "build_result": {"success": True},
                "unit_test_result": {"success": True},
                "warnings": [],
            }

    monkeypatch.setattr("agent_core.tools.geant4_runner.Geant4Runner", FakeRunner)

    result = await run_base_gates(
        {
            "job_id": job_id,
            "run_mode": "strict",
            "context_decision": "allow_rag",
            "task_spec": {"simulation_scope": ["geant4"]},
            "g4_model_ir": {"sources": [{"events": 5}]},
            "generated_code_dir": str(code_dir),
            "visual_review_status": "approved",
            "gate_results": [],
            "skipped_gates": [],
            "failed_gates": [],
        }
    )

    gates = {gate["gate_id"]: gate for gate in result["gate_results"]}
    assert seen["events"] == 5
    assert gates[6]["status"] == "pass"
    assert gates[9]["checked_items"] == [
        {"item": "smoke simulation (5 events)", "result": "pass"}
    ]


@pytest.mark.asyncio
async def test_visual_review_gate_is_retired_and_does_not_block(
    tmp_path: Path,
) -> None:
    code_dir = tmp_path / "generated_code"
    code_dir.mkdir()
    (code_dir / "CMakeLists.txt").write_text(
        "find_package(Geant4 REQUIRED ui_all vis_all)\nadd_executable(sim main.cc)\n",
        encoding="utf-8",
    )

    result = await run_visual_review_gate(
        {
            "task_spec": {"simulation_scope": ["geant4"]},
            "generated_code_dir": str(code_dir),
            "gate_results": [],
            "failed_gates": [],
        }
    )

    assert result["gate_results"] == []
    assert result["failed_gates"] == []

    approved = await run_visual_review_gate(
        {
            "task_spec": {"simulation_scope": ["geant4"]},
            "generated_code_dir": str(code_dir),
            "visual_review_status": "approved",
            "visual_review_notes": "inspected detector and target geometry",
            "gate_results": [],
            "failed_gates": [],
        }
    )
    assert approved["gate_results"] == []
    assert approved["failed_gates"] == []


async def test_visual_review_gate_is_retired_in_test_mode(
    tmp_path: Path,
) -> None:
    code_dir = tmp_path / "generated_code"
    code_dir.mkdir()
    (code_dir / "CMakeLists.txt").write_text(
        "find_package(Geant4 REQUIRED ui_all vis_all)\nadd_executable(sim main.cc)\n",
        encoding="utf-8",
    )

    result = await run_visual_review_gate(
        {
            "run_mode": "test",
            "task_spec": {"simulation_scope": ["geant4"]},
            "generated_code_dir": str(code_dir),
            "gate_results": [],
            "failed_gates": [],
        }
    )

    assert result["gate_results"] == []
    assert result["failed_gates"] == []
