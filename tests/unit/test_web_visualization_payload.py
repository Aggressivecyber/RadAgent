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


def test_visualization_payload_repairs_default_cylinder_radius_from_model_ir(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "geometry_view.json",
        {
            "units": {"length": "mm"},
            "components": [
                {
                    "id": "hpge_crystal",
                    "name": "Coaxial HPGe Crystal",
                    "shape": "cylinder",
                    "material": "G4_Ge",
                    "size_mm": [1.0, 1.0, 60.0],
                    "position_mm": [0.0, 0.0, 0.0],
                }
            ],
        },
    )
    model_ir = {
        "unit_contract": {"length_unit": "um", "coordinate_unit": "um"},
        "components": [
            {
                "component_id": "hpge_crystal",
                "display_name": "Coaxial HPGe Crystal",
                "geometry_type": "cylinder",
                "material_id": "G4_Ge",
                "dimensions": {"r": 40000.0, "dz": 60000.0},
                "placement": {"position": [0, 0, 0], "rotation": [0, 0, 0]},
            }
        ],
    }

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-visual",
        model_ir=model_ir,
        visual_events=100,
    )

    component = payload["geometry"]["components"][0]
    assert component["size_mm"] == [80.0, 80.0, 60.0]
    assert "geometry_view.json cylinder radius repaired from model IR for hpge_crystal" in payload["warnings"]


def test_visualization_payload_includes_source_rays_from_model_ir(
    tmp_path: Path,
) -> None:
    model_ir = {
        "global_units": {"length": "um"},
        "sources": [
            {
                "source_id": "primary_gamma",
                "particle_type": "gamma",
                "energy": {"value": 662.0, "unit": "keV"},
                "beam": {
                    "position": [0.0, 0.0, -150500.0],
                    "direction": [0.0, 0.0, 1.0],
                },
            }
        ],
        "components": [
            {
                "component_id": "hpge_crystal",
                "geometry_type": "cylinder",
                "dimensions": {"r": 40000.0, "dz": 60000.0},
                "placement": {"position": [0.0, 0.0, 0.0]},
            }
        ],
    }

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-source-ray",
        model_ir=model_ir,
        visual_events=100,
    )

    assert payload["source_rays"] == [
        {
            "source_id": "primary_gamma",
            "particle": "gamma",
            "energy": {"value": 662.0, "unit": "keV"},
            "start_mm": [0.0, 0.0, -150.5],
            "end_mm": [0.0, 0.0, 36.4],
        }
    ]


def test_visualization_payload_uses_coordinate_unit_for_source_ray_position(
    tmp_path: Path,
) -> None:
    model_ir = {
        "global_units": {"length": "mm"},
        "coordinate_system": {"unit": "um"},
        "sources": [
            {
                "source_id": "primary_gamma",
                "particle_type": "gamma",
                "energy": {"value": 662.0, "unit": "keV"},
                "beam": {
                    "position": [0.0, 0.0, -150500.0],
                    "direction": [0.0, 0.0, 1.0],
                },
            }
        ],
        "components": [
            {
                "component_id": "bgo_crystal",
                "geometry_type": "box",
                "dimensions": {"dx": 80.0, "dy": 80.0, "dz": 60.0},
                "placement": {"position": [0.0, 0.0, 0.0]},
            }
        ],
    }

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-source-ray-units",
        model_ir=model_ir,
        visual_events=100,
    )

    assert payload["source_rays"][0]["start_mm"] == [0.0, 0.0, -150.5]
    assert payload["source_rays"][0]["end_mm"][2] > 30.0


def test_visualization_payload_expands_rectangle_source_into_parallel_preview_rays(
    tmp_path: Path,
) -> None:
    model_ir = {
        "global_units": {"length": "um"},
        "sources": [
            {
                "source_id": "gamma_face",
                "particle_type": "gamma",
                "energy": {"value": 662.0, "unit": "keV"},
                "beam": {
                    "position": [0.0, 0.0, -100000.0],
                    "direction": [0.0, 0.0, 1.0],
                    "surface_shape": "rectangle",
                    "surface_size": [20000.0, 10000.0],
                },
            }
        ],
        "components": [
            {
                "component_id": "detector",
                "geometry_type": "box",
                "dimensions": {"dx": 40000.0, "dy": 40000.0, "dz": 10000.0},
                "placement": {"position": [0.0, 0.0, 0.0]},
            }
        ],
    }

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-face-source",
        model_ir=model_ir,
        visual_events=100,
    )

    starts = sorted(ray["start_mm"] for ray in payload["source_rays"])
    assert starts == [
        [-10.0, -5.0, -100.0],
        [-10.0, 5.0, -100.0],
        [0.0, 0.0, -100.0],
        [10.0, -5.0, -100.0],
        [10.0, 5.0, -100.0],
    ]
    assert {ray["particle"] for ray in payload["source_rays"]} == {"gamma"}
    assert {ray["end_mm"][2] > 0.0 for ray in payload["source_rays"]} == {True}


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
