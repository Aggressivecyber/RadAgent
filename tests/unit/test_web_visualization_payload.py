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


def test_visualization_payload_groups_flat_step_rows_into_tracks(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "geometry_view.json",
        {
            "components": [
                {
                    "id": "moderator",
                    "shape": "box",
                    "material": "G4_POLYETHYLENE",
                    "size_mm": [10.0, 10.0, 10.0],
                    "position_mm": [0.0, 0.0, 0.0],
                }
            ],
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
                    "position_mm": [0.0, 0.0, -5.0],
                    "kinetic_MeV": 14.0,
                },
                {
                    "event_id": 0,
                    "track_id": 1,
                    "particle": "neutron",
                    "position_mm": [0.0, 0.0, 0.0],
                    "kinetic_MeV": 13.8,
                },
                {
                    "event_id": 0,
                    "track_id": 1,
                    "particle": "neutron",
                    "position_mm": [0.0, 0.0, 5.0],
                    "kinetic_MeV": 13.4,
                },
            ],
        },
    )
    _write_json(
        tmp_path / "energy_deposits.json",
        {
            "deposits": [
                {
                    "event_id": 0,
                    "track_id": 1,
                    "volume": "moderator",
                    "position_mm": [0.0, 0.0, 0.0],
                    "edep_MeV": 0.25,
                }
            ]
        },
    )

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-flat-tracks",
        model_ir={},
        visual_events=100,
    )

    assert payload["status"] == "ready"
    assert payload["tracks"] == [
        {
            "event_id": 0,
            "track_id": 1,
            "particle": "neutron",
            "energy_MeV": 14.0,
            "points_mm": [[0.0, 0.0, -5.0], [0.0, 0.0, 0.0], [0.0, 0.0, 5.0]],
        }
    ]
    assert payload["stats"]["track_points"] == 3


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
            "source_shape": "point",
            "direction_mode": "mono",
            "sample_index": 0,
            "sample_count": 1,
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
    assert {ray["source_shape"] for ray in payload["source_rays"]} == {"rectangle"}
    assert {ray["direction_mode"] for ray in payload["source_rays"]} == {"mono"}
    assert {ray["sample_count"] for ray in payload["source_rays"]} == {5}
    assert {ray["end_mm"][2] > 0.0 for ray in payload["source_rays"]} == {True}


def test_visualization_payload_expands_random_point_source_into_ten_preview_rays(
    tmp_path: Path,
) -> None:
    model_ir = {
        "global_units": {"length": "mm"},
        "sources": [
            {
                "source_id": "iso_point",
                "particle_type": "gamma",
                "energy": {"value": 1.0, "unit": "MeV"},
                "beam": {
                    "position": [0.0, 0.0, 0.0],
                    "direction": [0.0, 0.0, 1.0],
                    "surface_shape": "point",
                    "angular_distribution": "isotropic",
                },
            }
        ],
        "components": [
            {
                "component_id": "detector",
                "geometry_type": "box",
                "dimensions": {"dx": 20.0, "dy": 20.0, "dz": 20.0},
                "placement": {"position": [0.0, 0.0, 0.0]},
            }
        ],
    }

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-random-point-source",
        model_ir=model_ir,
        visual_events=100,
    )

    assert len(payload["source_rays"]) == 10
    assert {tuple(ray["start_mm"]) for ray in payload["source_rays"]} == {(0.0, 0.0, 0.0)}
    assert {ray["source_shape"] for ray in payload["source_rays"]} == {"point"}
    assert {ray["direction_mode"] for ray in payload["source_rays"]} == {"random"}
    assert {ray["sample_count"] for ray in payload["source_rays"]} == {10}
    assert len({tuple(ray["end_mm"]) for ray in payload["source_rays"]}) > 6


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
    assert payload["analysis"]["source"] == "full_run"
    assert payload["analysis"]["stats"]["track_count"] == 105
    assert payload["analysis"]["particle_counts"] == [{"particle": "proton", "count": 105}]
    assert payload["deposits"][0]["event_id"] == 104
    assert "particle_tracks.json limited to 100 visual tracks" in payload["warnings"]


def test_visualization_payload_builds_full_run_energy_heatmap_analysis(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "particle_tracks.json",
        {
            "tracks": [
                {"event_id": 0, "track_id": 1, "particle": "neutron", "points_mm": [[0, 0, -1], [0, 0, 1]]},
                {"event_id": 1, "track_id": 2, "particle": "gamma", "points_mm": [[0, 0, -1], [0, 0, 1]]},
                {"event_id": 2, "track_id": 3, "particle": "neutron", "points_mm": [[0, 0, -1], [0, 0, 1]]},
            ]
        },
    )
    _write_json(
        tmp_path / "energy_deposits.json",
        {
            "deposits": [
                {"event_id": 0, "track_id": 1, "position_mm": [-1, 0, -2], "edep_MeV": 0.1},
                {"event_id": 1, "track_id": 2, "position_mm": [0, 0, 0], "edep_MeV": 0.5},
                {"event_id": 2, "track_id": 3, "position_mm": [1, 0, 2], "edep_MeV": 0.2},
            ]
        },
    )

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-analysis",
        model_ir={},
        visual_events=1,
    )

    analysis = payload["analysis"]
    assert len(payload["tracks"]) == 1
    assert analysis["stats"] == {
        "track_count": 3,
        "deposit_count": 3,
        "total_edep_MeV": 0.8,
    }
    assert analysis["particle_counts"] == [
        {"particle": "neutron", "count": 2},
        {"particle": "gamma", "count": 1},
    ]
    assert analysis["energy_points"][1] == {"x": 0.0, "y": 0.0, "z": 0.0, "edep_MeV": 0.5}
    assert analysis["slice_planes"]["z"]["values"]


def test_visualization_payload_samples_heatmap_points_but_keeps_full_energy_total(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "particle_tracks.json",
        {
            "tracks": [
                {"event_id": 0, "track_id": 1, "particle": "proton", "points_mm": [[0, 0, -1], [0, 0, 1]]},
            ]
        },
    )
    _write_json(
        tmp_path / "energy_deposits.json",
        {
            "deposits": [
                {
                    "event_id": index,
                    "track_id": 1,
                    "position_mm": [index % 10, (index // 10) % 10, index % 25],
                    "edep_MeV": 1.0,
                }
                for index in range(8001)
            ]
        },
    )

    payload = build_visualization_payload(
        output_dir=tmp_path,
        job_id="job-analysis-sampled",
        model_ir={},
        visual_events=100,
    )

    analysis = payload["analysis"]
    assert analysis["stats"]["deposit_count"] == 8001
    assert analysis["stats"]["total_edep_MeV"] == 8001.0
    assert len(analysis["energy_points"]) <= 8000
