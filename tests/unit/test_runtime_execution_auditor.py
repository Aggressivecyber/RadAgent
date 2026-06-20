from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agent_core.g4_codegen.runtime_execution_auditor import (
    collect_runtime_execution_facts,
    run_runtime_execution_auditor,
    runtime_audit_to_runtime_observation,
)
from agent_core.models.schemas import ModelCallResult, ModelProvider, ModelTask, ModelTier
from agent_core.workspace.paths import STAGE_CODEGEN


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_visual_artifacts(output_dir: Path) -> None:
    _write_json(
        output_dir / "geometry_view.json",
        {
            "components": [
                {
                    "id": "detector",
                    "name": "Detector",
                    "shape": "box",
                    "material": "G4_Si",
                    "size_mm": [1.0, 1.0, 1.0],
                    "position_mm": [0.0, 0.0, 0.0],
                    "rotation_deg": [0.0, 0.0, 0.0],
                    "opacity": 0.7,
                }
            ]
        },
    )
    _write_json(
        output_dir / "particle_tracks.json",
        {
            "tracks": [
                {
                    "event_id": 0,
                    "track_id": 1,
                    "particle": "proton",
                    "energy_MeV": 10.0,
                    "points_mm": [[0.0, 0.0, -1.0], [0.0, 0.0, 0.0]],
                }
            ]
        },
    )
    _write_json(
        output_dir / "energy_deposits.json",
        {
            "deposits": [
                {
                    "event_id": 0,
                    "track_id": 1,
                    "volume": "detector",
                    "position_mm": [0.0, 0.0, 0.0],
                    "edep_MeV": 1.0,
                }
            ]
        },
    )


def _attempt_dirs(tmp_path: Path, job_id: str = "runtime_audit") -> tuple[Path, Path, Path]:
    attempt_dir = tmp_path / "jobs" / job_id / STAGE_CODEGEN / "integration" / "runtime_attempt_1"
    project_dir = attempt_dir / "geant4_project"
    output_dir = attempt_dir / "g4_output_package"
    project_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    return attempt_dir, project_dir, output_dir


def _global_report(
    project_dir: Path,
    output_dir: Path,
    status: str = "pass",
    expected_events: int | None = None,
) -> dict[str, Any]:
    gate: dict[str, Any] = {
        "attempt": 1,
        "status": status,
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "build_result": {"success": True},
        "cmake_configure_result": {"success": True},
    }
    if expected_events is not None:
        gate["expected_events"] = expected_events
    return {
        "status": "passed",
        "runtime_gate_attempts": [gate],
    }


def _install_flash_auditor(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    class Gateway:
        profiles = {ModelTier.LITE: SimpleNamespace(provider=ModelProvider.OPENAI_COMPATIBLE)}

        async def call(self, **kwargs: Any) -> ModelCallResult:
            calls.append(kwargs)
            return ModelCallResult(
                task=kwargs["task"],
                tier=kwargs["tier"],
                provider=ModelProvider.OPENAI_COMPATIBLE,
                model_name="flash-test",
                content=json.dumps(
                    {
                        "status": "pass",
                        "actually_ran": True,
                        "artifact_contract_passed": True,
                        "data_trustworthy": True,
                        "findings": [],
                        "required_fixes": [],
                        "reviewer_notes": "deterministic facts reviewed",
                    }
                ),
                parsed_json=None,
                latency_ms=5.0,
            )

    monkeypatch.setattr(
        "agent_core.g4_codegen.runtime_execution_auditor.get_model_gateway",
        lambda: Gateway(),
    )


@pytest.mark.asyncio
async def test_runtime_auditor_uses_lite_and_rejects_success_with_geant4_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    calls: list[dict[str, Any]] = []
    _install_flash_auditor(monkeypatch, calls)
    attempt_dir, project_dir, output_dir = _attempt_dirs(tmp_path)
    (project_dir / "macros").mkdir()
    (project_dir / "macros" / "run.mac").write_text("/run/beamOn 10\n", encoding="utf-8")
    _write_json(
        output_dir / "smoke_simulation_result.json",
        {
            "success": True,
            "process_success": True,
            "errors": "***** COMMAND NOT FOUND </score/create/boxMesh siliconMesh> *****\n",
        },
    )
    _write_json(
        attempt_dir / "runtime_gate_result.json",
        _global_report(project_dir, output_dir, status="fail")["runtime_gate_attempts"][0],
    )

    audit = await run_runtime_execution_auditor(
        job_id="runtime_audit",
        global_integration_report=_global_report(project_dir, output_dir, status="fail"),
    )

    assert calls
    assert calls[0]["task"] == ModelTask.CONTEXT_SUMMARY
    assert calls[0]["tier"] == ModelTier.LITE
    assert calls[0]["metadata"]["module_name"] == "runtime_execution_auditor"
    assert calls[0]["metadata"]["enable_thinking"] is False
    assert audit["status"] == "fail"
    assert audit["actually_ran"] is False
    assert any("COMMAND NOT FOUND" in error for error in audit["blocking_errors"])
    assert any("Missing output contract files" in error for error in audit["blocking_errors"])


@pytest.mark.asyncio
async def test_runtime_auditor_passes_native_nonzero_output_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    calls: list[dict[str, Any]] = []
    _install_flash_auditor(monkeypatch, calls)
    _, project_dir, output_dir = _attempt_dirs(tmp_path)
    (project_dir / "macros").mkdir()
    (project_dir / "macros" / "run.mac").write_text("/run/beamOn 2\n", encoding="utf-8")
    _write_json(output_dir / "smoke_simulation_result.json", {"success": True, "errors": ""})
    _write_json(output_dir / "g4_summary.json", {"job_id": "runtime_audit", "events_requested": 2})
    _write_json(output_dir / "provenance.json", {"job_id": "runtime_audit", "source": "program"})
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.0,0.01\n1,0.5,0.005\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,1.0\n1,0,0,0.5\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n1,0,0,0.005\n",
        encoding="utf-8",
    )
    _write_visual_artifacts(output_dir)

    audit = await run_runtime_execution_auditor(
        job_id="runtime_audit",
        global_integration_report=_global_report(project_dir, output_dir),
    )

    assert audit["status"] == "pass"
    assert audit["actually_ran"] is True
    assert audit["artifact_contract_passed"] is True
    assert audit["data_trustworthy"] is True


def test_runtime_facts_reject_build_dir_event_table_and_identical_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    _, project_dir, output_dir = _attempt_dirs(tmp_path)
    (project_dir / "macros").mkdir()
    (project_dir / "macros" / "run.mac").write_text("/run/beamOn 1000\n", encoding="utf-8")
    (project_dir / "build").mkdir()
    (project_dir / "build" / "event_table.csv").write_text(
        "event_id,energy_deposit_MeV\n" + "\n".join(f"{i},10.000000" for i in range(1000)),
        encoding="utf-8",
    )
    _write_json(output_dir / "smoke_simulation_result.json", {"success": True, "errors": ""})
    _write_json(
        output_dir / "g4_summary.json",
        {"job_id": "runtime_audit", "events_requested": 10, "materialized_by_runner": True},
    )
    _write_json(output_dir / "provenance.json", {"materialized_by_runner": True})

    facts = collect_runtime_execution_facts(
        job_id="runtime_audit",
        global_integration_report=_global_report(project_dir, output_dir, status="fail"),
    )

    assert facts["data_trustworthy"] is False
    assert any("run.mac requests 1000 events" in error for error in facts["blocking_errors"])
    assert any("build/event_table.csv" in error for error in facts["blocking_errors"])
    assert any("one identical value" in error for error in facts["blocking_errors"])
    assert any("materialized by Geant4Runner" in error for error in facts["blocking_errors"])


def test_runtime_facts_reject_geometry_view_shape_that_conflicts_with_model_ir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    _, project_dir, output_dir = _attempt_dirs(tmp_path)
    (project_dir / "macros").mkdir()
    (project_dir / "macros" / "run.mac").write_text("/run/beamOn 2\n", encoding="utf-8")

    model_ir_path = tmp_path / "jobs" / "runtime_audit" / "03_model_ir" / "g4_model_ir.json"
    _write_json(
        model_ir_path,
        {
            "global_units": {"length": "mm"},
            "components": [
                {
                    "component_id": "detector",
                    "display_name": "HPGe crystal",
                    "geometry_type": "cylinder",
                    "dimensions": {"r": 30.0, "dz": 50.0},
                    "material_id": "G4_Ge",
                    "placement": {"position": [0.0, 0.0, 0.0]},
                }
            ],
        },
    )
    _write_json(output_dir / "smoke_simulation_result.json", {"success": True, "errors": ""})
    _write_json(output_dir / "g4_summary.json", {"job_id": "runtime_audit", "events_requested": 2})
    _write_json(output_dir / "provenance.json", {"job_id": "runtime_audit", "source": "program"})
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.0,0.01\n1,0.5,0.005\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,1.0\n1,0,0,0.5\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n1,0,0,0.005\n",
        encoding="utf-8",
    )
    _write_visual_artifacts(output_dir)

    facts = collect_runtime_execution_facts(
        job_id="runtime_audit",
        global_integration_report=_global_report(project_dir, output_dir, expected_events=2),
    )

    assert facts["data_trustworthy"] is False
    assert any(
        "geometry_view.json shape mismatch for detector" in error
        for error in facts["blocking_errors"]
    )


def test_event_table_reports_non_numeric_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    _, _project_dir, output_dir = _attempt_dirs(tmp_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,not-a-number,0.01\n1,0.5,bad\n",
        encoding="utf-8",
    )

    facts = collect_runtime_execution_facts(
        job_id="runtime_audit",
        global_integration_report=_global_report(_project_dir, output_dir),
    )

    warnings = facts["event_table"]["warnings"]
    assert "column edep_MeV has 1 non-numeric value(s)" in warnings
    assert "column dose_Gy has 1 non-numeric value(s)" in warnings


def test_runtime_facts_reject_event_count_below_runtime_gate_expectation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    _, project_dir, output_dir = _attempt_dirs(tmp_path)
    (project_dir / "macros").mkdir()
    (project_dir / "macros" / "run.mac").write_text("/run/beamOn 10\n", encoding="utf-8")
    _write_json(output_dir / "smoke_simulation_result.json", {"success": True, "errors": ""})
    _write_json(output_dir / "g4_summary.json", {"job_id": "runtime_audit", "events_requested": 10})
    _write_json(output_dir / "provenance.json", {"job_id": "runtime_audit", "source": "program"})
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n" + "\n".join(f"{i},1.0,0.01" for i in range(10)) + "\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,1.0\n",
        encoding="utf-8",
    )
    (output_dir / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n",
        encoding="utf-8",
    )

    facts = collect_runtime_execution_facts(
        job_id="runtime_audit",
        global_integration_report=_global_report(project_dir, output_dir, expected_events=1000),
    )

    assert facts["data_trustworthy"] is False
    assert facts["expected_events"] == 1000
    assert any("expected 1000 events" in error for error in facts["blocking_errors"])


def test_runtime_audit_observation_includes_artifact_paths() -> None:
    observation = runtime_audit_to_runtime_observation(
        {
            "status": "fail",
            "blocking_errors": ["bad runtime"],
            "required_fixes": [{"target": "run.mac", "message": "fix beamOn"}],
            "facts": {"artifact_paths": ["/tmp/runtime_gate_result.json"]},
        }
    )

    assert observation["phase"] == "runtime_execution_audit"
    assert observation["errors"] == ["run.mac: fix beamOn"]
    assert observation["artifacts"] == [{"path": "/tmp/runtime_gate_result.json"}]
