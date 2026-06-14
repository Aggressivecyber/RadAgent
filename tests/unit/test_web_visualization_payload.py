from __future__ import annotations

import json
from pathlib import Path

from agent_core.web.visualization import build_visualization_payload


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_visualization_payload_loads_real_tracks_deposits_and_geometry(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "geometry_view.json",
        {
            "units": {"length": "mm"},
            "components": [
                {
                    "id": "silicon_detector",
                    "name": "Silicon Detector",
                    "shape": "box",
                    "material": "G4_Si",
                    "size_mm": [10.0, 10.0, 0.3],
                    "position_mm": [0.0, 0.0, 0.0],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "particle_tracks.json",
        {
            "events": 100,
            "tracks": [
                {
                    "event_id": 7,
                    "track_id": 1,
                    "particle": "proton",
                    "energy_MeV": 10.0,
                    "points_mm": [[0.0, 0.0, -5.0], [0.0, 0.0, 0.0], [0.2, 0.0, 4.5]],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "energy_deposits.json",
        {
            "deposits": [
                {
                    "event_id": 7,
                    "track_id": 1,
                    "volume": "silicon_detector",
                    "position_mm": [0.0, 0.0, 0.0],
                    "edep_MeV": 0.42,
                }
            ]
        },
    )

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-visual",
        model_ir={},
        visual_events=100,
    )

    assert payload["status"] == "ready"
    assert payload["job_id"] == "job-visual"
    assert payload["source"]["visual_events"] == 100
    assert payload["geometry"]["components"][0]["id"] == "silicon_detector"
    assert payload["tracks"][0]["points_mm"][-1] == [0.2, 0.0, 4.5]
    assert payload["deposits"][0]["edep_MeV"] == 0.42
    assert payload["stats"] == {
        "components": 1,
        "tracks": 1,
        "track_points": 3,
        "deposits": 1,
    }


def test_visualization_payload_marks_missing_tracks_without_inventing_fake_data(
    tmp_path: Path,
) -> None:
    (tmp_path / "edep_3d.csv").write_text(
        "cellId,x_mm,y_mm,z_mm,edep_MeV\n0,1,2,3,0.25\n",
        encoding="utf-8",
    )
    model_ir = {
        "components": [
            {
                "component_id": "world",
                "display_name": "World",
                "geometry_type": "box",
                "material_id": "G4_AIR",
                "dimensions": {"dx": 20, "dy": 20, "dz": 20},
                "placement": {"position": [0, 0, 0], "rotation": [0, 0, 0]},
            }
        ]
    }

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-partial",
        model_ir=model_ir,
        visual_events=100,
    )

    assert payload["status"] == "partial"
    assert payload["tracks"] == []
    assert payload["deposits"][0]["position_mm"] == [1.0, 2.0, 3.0]
    assert "particle_tracks.json missing" in payload["warnings"]
    assert payload["geometry"]["components"][0]["id"] == "world"


def test_visualization_payload_caps_browser_tracks_to_visual_event_budget(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "geometry_view.json",
        {
            "components": [
                {
                    "id": "detector",
                    "shape": "box",
                    "material": "G4_Si",
                    "size_mm": [1, 1, 1],
                    "position_mm": [0, 0, 0],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "particle_tracks.json",
        {
            "tracks": [
                {
                    "event_id": index,
                    "track_id": index + 1,
                    "particle": "proton",
                    "points_mm": [[0, 0, -1], [0, 0, 1]],
                }
                for index in range(105)
            ]
        },
    )
    _write_json(
        tmp_path / "energy_deposits.json",
        {
            "deposits": [
                {
                    "event_id": 104,
                    "track_id": 105,
                    "volume": "detector",
                    "position_mm": [0, 0, 0],
                    "edep_MeV": 0.1,
                }
            ]
        },
    )

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-visual-limit",
        model_ir={},
        visual_events=100,
    )

    assert payload["status"] == "ready"
    assert len(payload["tracks"]) == 100
    assert payload["stats"]["tracks"] == 100
    assert payload["stats"]["track_points"] == 200
    assert payload["deposits"][0]["event_id"] == 104
    assert "particle_tracks.json limited to 100 visual tracks" in payload["warnings"]
