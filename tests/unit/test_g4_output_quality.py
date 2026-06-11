from __future__ import annotations

import json
from pathlib import Path

from agent_core.gates.output_quality import inspect_g4_output_quality


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_output_quality_rejects_empty_event_table_all_zero_mesh_and_bad_stderr(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 10})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    (tmp_path / "event_table.csv").write_text("EventID,edep_MeV,dose_Gy\n", encoding="utf-8")
    (tmp_path / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,0\n1,0,0,0\n",
        encoding="utf-8",
    )
    (tmp_path / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0\n1,0,0,0\n",
        encoding="utf-8",
    )

    report = inspect_g4_output_quality(
        tmp_path,
        smoke_result={
            "success": True,
            "errors": "parameter value (Phantom) is not listed in the candidate List.",
        },
    )

    assert not report.passed
    assert "event_table.csv has no event rows" in report.errors
    assert "edep_3d.csv has no non-zero edep_MeV bins" in report.errors
    assert "dose_3d.csv has no non-zero dose_Gy bins" in report.errors
    assert any(error.startswith("Smoke simulation stderr contains:") for error in report.errors)


def test_output_quality_accepts_populated_nonzero_outputs(tmp_path: Path) -> None:
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 2})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    (tmp_path / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.25,0.01\n1,0.50,0.004\n",
        encoding="utf-8",
    )
    (tmp_path / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,1.25\n1,0,0,0.50\n",
        encoding="utf-8",
    )
    (tmp_path / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n1,0,0,0.004\n",
        encoding="utf-8",
    )

    report = inspect_g4_output_quality(tmp_path, smoke_result={"success": True, "errors": ""})

    assert report.passed
    assert report.metrics["event_table_rows"] == 2
    assert report.metrics["edep_3d_nonzero_rows"] == 2
    assert report.metrics["dose_3d_nonzero_rows"] == 2


def test_output_quality_rejects_outputs_below_expected_event_count(tmp_path: Path) -> None:
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 10})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    (tmp_path / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n" + "\n".join(f"{i},1.0,0.01" for i in range(10)) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n",
        encoding="utf-8",
    )

    report = inspect_g4_output_quality(
        tmp_path,
        smoke_result={"success": True, "errors": ""},
        expected_events=1000,
    )

    assert not report.passed
    assert report.metrics["expected_events"] == 1000
    assert any("expected 1000" in error for error in report.errors)


def test_output_quality_accepts_unit_suffixed_mesh_coordinates(tmp_path: Path) -> None:
    (tmp_path / "g4_summary.json").write_text('{"events_requested": 1}', encoding="utf-8")
    (tmp_path / "provenance.json").write_text("{}", encoding="utf-8")
    (tmp_path / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.0,0.01\n",
        encoding="utf-8",
    )
    (tmp_path / "edep_3d.csv").write_text(
        "cellId,x_mm,y_mm,z_mm,edep_MeV\n0,0,0,0,1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "dose_3d.csv").write_text(
        "cellId,x_mm,y_mm,z_mm,dose_Gy\n0,0,0,0,0.01\n",
        encoding="utf-8",
    )

    report = inspect_g4_output_quality(tmp_path, smoke_result={"success": True, "errors": ""})

    assert report.passed


def test_output_quality_rejects_geant4_command_not_found_stderr(tmp_path: Path) -> None:
    (tmp_path / "g4_summary.json").write_text('{"events_requested": 1}', encoding="utf-8")
    (tmp_path / "provenance.json").write_text("{}", encoding="utf-8")
    (tmp_path / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,1.0,0.01\n",
        encoding="utf-8",
    )
    (tmp_path / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,1.0\n",
        encoding="utf-8",
    )
    (tmp_path / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n",
        encoding="utf-8",
    )

    report = inspect_g4_output_quality(
        tmp_path,
        smoke_result={
            "success": True,
            "errors": "***** COMMAND NOT FOUND </score/create/boxMesh siliconMesh> *****",
        },
    )

    assert not report.passed
    assert any("COMMAND NOT FOUND" in error for error in report.errors)
