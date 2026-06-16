from __future__ import annotations

import json
from pathlib import Path

from agent_core.gates.output_quality import inspect_g4_output_quality


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_visual_artifacts(path: Path) -> None:
    _write_json(
        path / "geometry_view.json",
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
                    "opacity": 0.6,
                }
            ]
        },
    )
    _write_json(
        path / "particle_tracks.json",
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
        path / "energy_deposits.json",
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


def test_output_quality_rejects_empty_event_table_all_zero_mesh_and_bad_stderr(
    tmp_path: Path,
) -> None:
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 10})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    _write_visual_artifacts(tmp_path)
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
    _write_visual_artifacts(tmp_path)
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


def test_output_quality_accepts_track_points_with_coordinate_objects(tmp_path: Path) -> None:
    """Project-agent output uses tracks[].points with x_mm/y_mm/z_mm objects."""
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 2})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    _write_json(
        tmp_path / "geometry_view.json",
        {
            "components": [
                {
                    "id": "shield",
                    "size_mm": [10.0, 10.0, 10.0],
                    "position_mm": [0.0, 0.0, 0.0],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "particle_tracks.json",
        {
            "tracks": [
                {
                    "event_id": 0,
                    "track_id": 1,
                    "particle": "neutron",
                    "points": [
                        {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 1.0, "ke_MeV": 14.0},
                        {"x_mm": 0.0, "y_mm": 0.0, "z_mm": -1.0, "ke_MeV": 13.5},
                    ],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "energy_deposits.json",
        {
            "deposits": [
                {
                    "event_id": 0,
                    "track_id": 1,
                    "volume": "shield",
                    "position": {"x_mm": 0.0, "y_mm": 0.0, "z_mm": 0.0},
                    "edep_MeV": 0.5,
                }
            ]
        },
    )
    (tmp_path / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,0.5,0.01\n1,0.2,0.004\n",
        encoding="utf-8",
    )
    (tmp_path / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,0.5\n1,0,0,0.2\n",
        encoding="utf-8",
    )
    (tmp_path / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n1,0,0,0.004\n",
        encoding="utf-8",
    )

    report = inspect_g4_output_quality(tmp_path, smoke_result={"success": True, "errors": ""})

    assert report.passed
    assert report.metrics["particle_track_points"] == 2
    assert report.metrics["particle_tracks_usable"] == 1


def test_output_quality_accepts_flat_track_point_records(tmp_path: Path) -> None:
    """The template writer emits tracks[] as individual step-point records."""
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 2})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    _write_json(
        tmp_path / "geometry_view.json",
        {
            "components": [
                {
                    "id": "shield",
                    "size_mm": [10.0, 10.0, 10.0],
                    "position_mm": [0.0, 0.0, 0.0],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "particle_tracks.json",
        {
            "tracks": [
                {
                    "event_id": 0,
                    "track_id": 7,
                    "particle": "neutron",
                    "position_mm": [0.0, 0.0, 1.0],
                    "kinetic_MeV": 14.0,
                },
                {
                    "event_id": 0,
                    "track_id": 7,
                    "particle": "neutron",
                    "position_mm": [0.0, 0.0, -1.0],
                    "kinetic_MeV": 13.5,
                },
            ]
        },
    )
    _write_json(
        tmp_path / "energy_deposits.json",
        {
            "deposits": [
                {
                    "event_id": 0,
                    "track_id": 7,
                    "volume": "shield",
                    "position_mm": [0.0, 0.0, 0.0],
                    "edep_MeV": 0.5,
                }
            ]
        },
    )
    (tmp_path / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,0.5,0.01\n1,0.2,0.004\n",
        encoding="utf-8",
    )
    (tmp_path / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,0.5\n1,0,0,0.2\n",
        encoding="utf-8",
    )
    (tmp_path / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n1,0,0,0.004\n",
        encoding="utf-8",
    )

    report = inspect_g4_output_quality(tmp_path, smoke_result={"success": True, "errors": ""})

    assert report.passed
    assert report.metrics["particle_track_points"] == 2
    assert report.metrics["particle_tracks_usable"] == 1


def test_output_quality_accepts_direct_xyz_energy_deposits(tmp_path: Path) -> None:
    """Project-agent artifacts may store deposit positions as direct x/y/z fields."""
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 2})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    _write_json(
        tmp_path / "geometry_view.json",
        {
            "components": [
                {
                    "id": "shield",
                    "size_mm": [10.0, 10.0, 10.0],
                    "position_mm": [0.0, 0.0, 0.0],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "particle_tracks.json",
        {
            "tracks": [
                {
                    "event_id": 0,
                    "track_id": 1,
                    "particle": "neutron",
                    "points": [
                        {"x": 0.0, "y": 0.0, "z": 1.0, "energy_keV": 14000.0},
                        {"x": 0.0, "y": 0.0, "z": -1.0, "energy_keV": 13500.0},
                    ],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "energy_deposits.json",
        {
            "deposits": [
                {
                    "event_id": 0,
                    "track_id": 1,
                    "volume": "shield",
                    "x": 0.0,
                    "y": 0.0,
                    "z": 0.0,
                    "edep_MeV": 0.5,
                }
            ]
        },
    )
    (tmp_path / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n0,0.5,0.01\n1,0.2,0.004\n",
        encoding="utf-8",
    )
    (tmp_path / "edep_3d.csv").write_text(
        "x,y,z,edep_MeV\n0,0,0,0.5\n1,0,0,0.2\n",
        encoding="utf-8",
    )
    (tmp_path / "dose_3d.csv").write_text(
        "x,y,z,dose_Gy\n0,0,0,0.01\n1,0,0,0.004\n",
        encoding="utf-8",
    )

    report = inspect_g4_output_quality(tmp_path, smoke_result={"success": True, "errors": ""})

    assert report.passed
    assert report.metrics["energy_deposits_positive"] == 1


def test_output_quality_rejects_outputs_below_expected_event_count(tmp_path: Path) -> None:
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 10})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    _write_visual_artifacts(tmp_path)
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
    _write_visual_artifacts(tmp_path)
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


def test_output_quality_rejects_all_zero_event_table_edep(tmp_path: Path) -> None:
    """Rows present but every edep is zero — the init-order / scoring-wiring canary.

    Reproduces the job_cbb4f07a false-success shape: event_table.csv has real
    rows yet all energy is zero because the scoring pointer was never wired.
    The 3D meshes are populated so the ONLY failure is the all-zero event table,
    isolating the new check.
    """
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 5})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
    _write_visual_artifacts(tmp_path)
    (tmp_path / "event_table.csv").write_text(
        "EventID,edep_MeV,dose_Gy\n" + "\n".join(f"{i},0.0,0.0" for i in range(5)) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "edep_3d.csv").write_text("x,y,z,edep_MeV\n0,0,0,1.0\n", encoding="utf-8")
    (tmp_path / "dose_3d.csv").write_text("x,y,z,dose_Gy\n0,0,0,0.01\n", encoding="utf-8")

    report = inspect_g4_output_quality(tmp_path, smoke_result={"success": True, "errors": ""})

    assert not report.passed
    assert report.metrics["event_table_nonzero_rows"] == 0
    joined = " ".join(report.errors)
    assert "no non-zero edep_MeV rows" in joined
    # Root-cause hint must steer the model at the actual fix.
    assert "CONSTRUCTOR" in joined
    assert "componentId" in joined


def test_output_quality_rejects_geant4_command_not_found_stderr(tmp_path: Path) -> None:
    (tmp_path / "g4_summary.json").write_text('{"events_requested": 1}', encoding="utf-8")
    (tmp_path / "provenance.json").write_text("{}", encoding="utf-8")
    _write_visual_artifacts(tmp_path)
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


def test_output_quality_rejects_empty_visual_workbench_artifacts(tmp_path: Path) -> None:
    _write_json(tmp_path / "g4_summary.json", {"job_id": "job", "events_requested": 1})
    _write_json(tmp_path / "provenance.json", {"job_id": "job"})
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
    _write_json(tmp_path / "geometry_view.json", {"components": []})
    _write_json(tmp_path / "particle_tracks.json", {"tracks": []})
    _write_json(tmp_path / "energy_deposits.json", {"deposits": []})

    report = inspect_g4_output_quality(tmp_path, smoke_result={"success": True, "errors": ""})

    assert not report.passed
    assert any("geometry_view.json has no components" in error for error in report.errors)
    assert any("particle_tracks.json has no usable tracks" in error for error in report.errors)
    assert any("energy_deposits.json has no positive deposits" in error for error in report.errors)
