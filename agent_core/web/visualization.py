from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

VISUAL_ARTIFACTS = (
    "geometry_view.json",
    "particle_tracks.json",
    "energy_deposits.json",
)
DEFAULT_VISUAL_TRACK_LIMIT = 100


def build_visualization_payload(
    *,
    output_dir: str | Path | None,
    job_id: str = "",
    model_ir: dict[str, Any] | None = None,
    visual_events: int = 100,
) -> dict[str, Any]:
    """Build the browser-facing 3D visualization payload from real artifacts."""
    root = Path(output_dir) if output_dir else None
    warnings: list[str] = []
    geometry = _load_geometry(root, model_ir or {}, warnings)
    tracks = _limit_visual_tracks(
        _load_tracks(root, warnings),
        visual_events=visual_events,
        warnings=warnings,
    )
    deposits = _load_deposits(root, warnings)

    if not deposits and root is not None:
        deposits = _load_deposits_from_edep_csv(root / "edep_3d.csv", warnings)

    stats = {
        "components": len(geometry["components"]),
        "tracks": len(tracks),
        "track_points": sum(len(track["points_mm"]) for track in tracks),
        "deposits": len(deposits),
    }
    status = _payload_status(stats, warnings)

    return {
        "status": status,
        "job_id": job_id,
        "source": {
            "output_dir": str(root) if root is not None else "",
            "visual_events": visual_events,
            "artifacts": {
                name: str(root / name) if root is not None and (root / name).is_file() else ""
                for name in VISUAL_ARTIFACTS
            },
        },
        "geometry": geometry,
        "tracks": tracks,
        "deposits": deposits,
        "stats": stats,
        "warnings": warnings,
    }


def _payload_status(stats: dict[str, int], warnings: list[str]) -> str:
    if stats["components"] and stats["tracks"] and stats["deposits"]:
        return "ready"
    if any(stats.values()):
        return "partial"
    return "waiting"


def _load_json(path: Path | None) -> Any:
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_geometry(
    root: Path | None,
    model_ir: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    data = _load_json(root / "geometry_view.json" if root is not None else None)
    if isinstance(data, dict):
        components = [_normalize_component(item) for item in _as_list(data.get("components"))]
        components = [item for item in components if item]
        if components:
            units = data.get("units") if isinstance(data.get("units"), dict) else {"length": "mm"}
            return {"units": units, "components": components}

    if root is not None:
        warnings.append("geometry_view.json missing")
    components = [
        _normalize_ir_component(item)
        for item in _as_list(model_ir.get("components"))
    ]
    return {
        "units": {"length": "mm"},
        "components": [item for item in components if item],
    }


def _load_tracks(root: Path | None, warnings: list[str]) -> list[dict[str, Any]]:
    path = root / "particle_tracks.json" if root is not None else None
    data = _load_json(path)
    if not isinstance(data, dict):
        if root is not None:
            warnings.append("particle_tracks.json missing")
        return []
    tracks = [_normalize_track(item) for item in _as_list(data.get("tracks"))]
    tracks = [item for item in tracks if item and len(item["points_mm"]) >= 2]
    if not tracks:
        warnings.append("particle_tracks.json has no usable tracks")
    return tracks


def _limit_visual_tracks(
    tracks: list[dict[str, Any]],
    *,
    visual_events: int,
    warnings: list[str],
) -> list[dict[str, Any]]:
    limit = max(1, _int(visual_events, DEFAULT_VISUAL_TRACK_LIMIT))
    if len(tracks) <= limit:
        return tracks
    warnings.append(f"particle_tracks.json limited to {limit} visual tracks")
    return tracks[:limit]


def _load_deposits(root: Path | None, warnings: list[str]) -> list[dict[str, Any]]:
    path = root / "energy_deposits.json" if root is not None else None
    data = _load_json(path)
    if not isinstance(data, dict):
        if root is not None:
            warnings.append("energy_deposits.json missing")
        return []
    deposits = [_normalize_deposit(item) for item in _as_list(data.get("deposits"))]
    deposits = [item for item in deposits if item and item["edep_MeV"] > 0.0]
    if not deposits:
        warnings.append("energy_deposits.json has no positive deposits")
    return deposits


def _load_deposits_from_edep_csv(path: Path, warnings: list[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    deposits: list[dict[str, Any]] = []
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader):
                edep = _float(row.get("edep_MeV"), 0.0)
                if edep <= 0.0:
                    continue
                deposits.append(
                    {
                        "event_id": _int(row.get("EventID"), index),
                        "track_id": _int(row.get("track_id"), 0),
                        "volume": str(row.get("volume") or row.get("Volume") or ""),
                        "position_mm": [
                            _float(row.get("x_mm", row.get("x")), 0.0),
                            _float(row.get("y_mm", row.get("y")), 0.0),
                            _float(row.get("z_mm", row.get("z")), 0.0),
                        ],
                        "edep_MeV": edep,
                    }
                )
    except OSError:
        return []
    if deposits:
        warnings.append("energy_deposits.json missing; derived deposits from edep_3d.csv")
    return deposits


def _normalize_component(value: Any) -> dict[str, Any]:
    row = _as_dict(value)
    component_id = _text(row.get("id") or row.get("component_id"))
    if not component_id:
        return {}
    size = _vector(row.get("size_mm") or row.get("size"), fallback=[1.0, 1.0, 1.0])
    return {
        "id": component_id,
        "name": _text(row.get("name") or row.get("display_name"), component_id),
        "shape": _text(row.get("shape") or row.get("geometry_type"), "box"),
        "material": _text(row.get("material") or row.get("material_id")),
        "role": _text(row.get("role") or row.get("component_type")),
        "size_mm": size,
        "position_mm": _vector(row.get("position_mm") or row.get("position")),
        "rotation_deg": _vector(row.get("rotation_deg") or row.get("rotation")),
        "color": _text(row.get("color")),
        "opacity": _float(row.get("opacity"), 0.36),
    }


def _normalize_ir_component(value: Any) -> dict[str, Any]:
    row = _as_dict(value)
    component_id = _text(row.get("component_id") or row.get("id"))
    if not component_id:
        return {}
    placement = _as_dict(row.get("placement"))
    dimensions = _as_dict(row.get("dimensions"))
    return {
        "id": component_id,
        "name": _text(row.get("display_name") or row.get("name"), component_id),
        "shape": _text(row.get("geometry_type") or row.get("shape"), "box"),
        "material": _text(row.get("material_id") or row.get("material")),
        "role": ",".join(str(item) for item in _as_list(row.get("roles"))),
        "size_mm": _dimension_size(dimensions),
        "position_mm": _vector(placement.get("position") or row.get("position")),
        "rotation_deg": _vector(placement.get("rotation") or row.get("rotation")),
        "color": "",
        "opacity": 0.22 if component_id.lower() == "world" else 0.42,
    }


def _dimension_size(dimensions: dict[str, Any]) -> list[float]:
    return [
        _dimension_axis(dimensions, "x"),
        _dimension_axis(dimensions, "y"),
        _dimension_axis(dimensions, "z"),
    ]


def _dimension_axis(dimensions: dict[str, Any], axis: str) -> float:
    if f"d{axis}" in dimensions:
        return _float(dimensions.get(f"d{axis}"), 1.0)
    if f"half_{axis}" in dimensions:
        return _float(dimensions.get(f"half_{axis}"), 0.5) * 2.0
    if axis in dimensions:
        return _float(dimensions.get(axis), 1.0)
    return 1.0


def _normalize_track(value: Any) -> dict[str, Any]:
    row = _as_dict(value)
    points = row.get("points_mm") or row.get("points") or row.get("steps")
    normalized_points = [_vector(item) for item in _as_list(points)]
    normalized_points = [point for point in normalized_points if len(point) == 3]
    return {
        "event_id": _int(row.get("event_id") or row.get("EventID"), 0),
        "track_id": _int(row.get("track_id"), 0),
        "particle": _text(row.get("particle"), "unknown"),
        "energy_MeV": _float(row.get("energy_MeV"), 0.0),
        "points_mm": normalized_points,
    }


def _normalize_deposit(value: Any) -> dict[str, Any]:
    row = _as_dict(value)
    position = row.get("position_mm") or row.get("position")
    if position is None:
        position = [row.get("x_mm", row.get("x")), row.get("y_mm", row.get("y")), row.get("z_mm", row.get("z"))]
    return {
        "event_id": _int(row.get("event_id") or row.get("EventID"), 0),
        "track_id": _int(row.get("track_id"), 0),
        "volume": _text(row.get("volume") or row.get("Volume")),
        "position_mm": _vector(position),
        "edep_MeV": _float(row.get("edep_MeV"), 0.0),
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _vector(value: Any, fallback: list[float] | None = None) -> list[float]:
    fallback = fallback or [0.0, 0.0, 0.0]
    if not isinstance(value, list) or len(value) < 3:
        return list(fallback)
    return [_float(value[0], fallback[0]), _float(value[1], fallback[1]), _float(value[2], fallback[2])]


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
