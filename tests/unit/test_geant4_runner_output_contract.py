from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from agent_core.tools.geant4_runner import Geant4Runner


def _runner() -> Geant4Runner:
    return Geant4Runner.__new__(Geant4Runner)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_materialize_output_contract_derives_3d_outputs_from_event_table(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    executable_dir = tmp_path / "build"
    output_dir.mkdir()
    executable_dir.mkdir()
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.5,0.01\n1,0.25,0.002\n",
        encoding="utf-8",
    )

    _runner()._materialize_output_contract(
        output_dir=str(output_dir),
        executable_dir=str(executable_dir),
        job_id="job",
        events=2,
        sim={"success": True},
    )

    edep_rows = _read_rows(output_dir / "edep_3d.csv")
    dose_rows = _read_rows(output_dir / "dose_3d.csv")
    assert edep_rows[0]["x_mm"] == "0"
    assert edep_rows[0]["edep_MeV"] == "1.5"
    assert dose_rows[1]["z_mm"] == "0"
    assert dose_rows[1]["dose_Gy"] == "0.002"
    summary = json.loads((output_dir / "g4_summary.json").read_text(encoding="utf-8"))
    assert summary["total_events"] == 2
    assert summary["events_requested"] == 2


def test_materialize_output_contract_replaces_unusable_zero_3d_outputs(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    executable_dir = tmp_path / "build"
    output_dir.mkdir()
    executable_dir.mkdir()
    (output_dir / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,2.0,0.02\n",
        encoding="utf-8",
    )
    (output_dir / "edep_3d.csv").write_text("EventID,edep_MeV\n0,0\n", encoding="utf-8")
    (output_dir / "dose_3d.csv").write_text("x,y,z,dose_Gy\n0,0,0,0\n", encoding="utf-8")

    _runner()._materialize_output_contract(
        output_dir=str(output_dir),
        executable_dir=str(executable_dir),
        job_id="job",
        events=1,
        sim={"success": True},
    )

    assert _read_rows(output_dir / "edep_3d.csv")[0]["edep_MeV"] == "2.0"
    assert _read_rows(output_dir / "dose_3d.csv")[0]["dose_Gy"] == "0.02"


@pytest.mark.asyncio
async def test_simulate_rejects_geant4_command_errors_even_with_zero_returncode(
    tmp_path: Path,
) -> None:
    runner = _runner()

    async def fake_run(cmd: str, cwd: str | None = None) -> tuple[int, str, str]:
        return (
            0,
            "",
            "***** COMMAND NOT FOUND </score/create/boxMesh siliconMesh> *****\n",
        )

    runner._run = fake_run  # type: ignore[method-assign]
    executable = tmp_path / "detector_sim"
    executable.write_text("", encoding="utf-8")

    result = await runner.simulate(str(executable), macro="run.mac")

    assert result["process_success"] is True
    assert result["success"] is False
    assert any("COMMAND NOT FOUND" in item for item in result["runtime_error_patterns"])
