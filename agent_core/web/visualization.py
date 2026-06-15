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
    source_rays = _source_rays_from_model_ir(model_ir or {}, geometry)

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
        "source_rays": source_rays,
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
            components = _repair_geometry_components_from_model_ir(components, model_ir, warnings)
            units = data.get("units") if isinstance(data.get("units"), dict) else {"length": "mm"}
            return {"units": units, "components": components}

    if root is not None:
        warnings.append("geometry_view.json missing")
    length_factor = _model_ir_length_factor(model_ir)
    coordinate_factor = _model_ir_coordinate_factor(model_ir)
    components = [
        _normalize_ir_component(item, length_factor=length_factor, coordinate_factor=coordinate_factor)
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


def _source_rays_from_model_ir(
    model_ir: dict[str, Any],
    geometry: dict[str, Any],
) -> list[dict[str, Any]]:
    coordinate_factor = _model_ir_coordinate_factor(model_ir)
    extent = _geometry_extent_mm(geometry)
    rays: list[dict[str, Any]] = []
    for source in _as_list(model_ir.get("sources")):
        row = _as_dict(source)
        beam = _as_dict(row.get("beam"))
        start = _scaled_vector_mm(beam.get("position"), coordinate_factor)
        direction = _normalize_direction(_vector(beam.get("direction"), fallback=[0.0, 0.0, 1.0]))
        if not direction:
            continue
        source_id = _text(row.get("source_id") or row.get("id"), f"source_{len(rays) + 1}")
        start_points = _source_preview_start_points_mm(start, direction, beam, coordinate_factor)
        for sample_index, sample_start in enumerate(start_points):
            length = _source_ray_length_mm(sample_start, direction, geometry, extent)
            end = [sample_start[index] + direction[index] * length for index in range(3)]
            rays.append(
                {
                    "source_id": source_id if sample_index == 0 else f"{source_id}:{sample_index}",
                    "particle": _text(row.get("particle_type") or row.get("particle"), "particle"),
                    "energy": _as_dict(row.get("energy")),
                    "start_mm": [_round_mm(value) for value in sample_start],
                    "end_mm": [_round_mm(value) for value in end],
                }
            )
    return rays


def _source_preview_start_points_mm(
    center: list[float],
    direction: list[float],
    beam: dict[str, Any],
    coordinate_factor: float,
) -> list[list[float]]:
    shape = _text(beam.get("surface_shape"), "point").lower()
    surface_size = _as_list(beam.get("surface_size"))
    axis_u, axis_v = _source_surface_basis(direction)

    if shape == "rectangle" and len(surface_size) >= 2:
        half_width = abs(_float(surface_size[0], 0.0) * coordinate_factor) / 2.0
        half_height = abs(_float(surface_size[1], 0.0) * coordinate_factor) / 2.0
        if half_width > 0.0 and half_height > 0.0:
            return [
                center,
                _offset_point(center, axis_u, axis_v, -half_width, -half_height),
                _offset_point(center, axis_u, axis_v, -half_width, half_height),
                _offset_point(center, axis_u, axis_v, half_width, -half_height),
                _offset_point(center, axis_u, axis_v, half_width, half_height),
            ]

    if shape == "circle" and surface_size:
        radius = abs(_float(surface_size[0], 0.0) * coordinate_factor)
        if radius > 0.0:
            return [
                center,
                _offset_point(center, axis_u, axis_v, radius, 0.0),
                _offset_point(center, axis_u, axis_v, -radius, 0.0),
                _offset_point(center, axis_u, axis_v, 0.0, radius),
                _offset_point(center, axis_u, axis_v, 0.0, -radius),
            ]

    return [center]


def _source_surface_basis(direction: list[float]) -> tuple[list[float], list[float]]:
    reference = [0.0, 1.0, 0.0] if abs(direction[1]) < 0.9 else [1.0, 0.0, 0.0]
    axis_u = _normalize_direction(_cross(reference, direction))
    if not axis_u:
        axis_u = [1.0, 0.0, 0.0]
    axis_v = _normalize_direction(_cross(direction, axis_u))
    if not axis_v:
        axis_v = [0.0, 1.0, 0.0]
    return axis_u, axis_v


def _offset_point(
    center: list[float],
    axis_u: list[float],
    axis_v: list[float],
    u_mm: float,
    v_mm: float,
) -> list[float]:
    return [
        center[index] + axis_u[index] * u_mm + axis_v[index] * v_mm
        for index in range(3)
    ]


def _cross(left: list[float], right: list[float]) -> list[float]:
    return [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]


def _source_ray_length_mm(
    start: list[float],
    direction: list[float],
    geometry: dict[str, Any],
    extent: float,
) -> float:
    bounds = _geometry_bounds_mm(geometry)
    if bounds is None:
        return max(extent * 1.5, 80.0)
    min_point, max_point = bounds
    corners = [
        [x, y, z]
        for x in (min_point[0], max_point[0])
        for y in (min_point[1], max_point[1])
        for z in (min_point[2], max_point[2])
    ]
    far_projection = max(
        sum((corner[index] - start[index]) * direction[index] for index in range(3))
        for corner in corners
    )
    return max(far_projection + extent * 0.08, 80.0)


def _geometry_extent_mm(geometry: dict[str, Any]) -> float:
    bounds = _geometry_bounds_mm(geometry)
    if bounds is None:
        return 50.0
    min_point, max_point = bounds
    return max(abs(max_point[index] - min_point[index]) for index in range(3)) or 50.0


def _geometry_bounds_mm(geometry: dict[str, Any]) -> tuple[list[float], list[float]] | None:
    components = [
        item
        for item in _as_list(geometry.get("components"))
        if isinstance(item, dict) and "world" not in _text(item.get("role") or item.get("id")).lower()
    ]
    if not components:
        components = [item for item in _as_list(geometry.get("components")) if isinstance(item, dict)]
    if not components:
        return None
    min_point = [float("inf"), float("inf"), float("inf")]
    max_point = [float("-inf"), float("-inf"), float("-inf")]
    for component in components:
        size = _vector(component.get("size_mm") or component.get("size"), fallback=[0.0, 0.0, 0.0])
        position = _vector(component.get("position_mm") or component.get("position"))
        for index in range(3):
            half = abs(size[index]) / 2.0
            min_point[index] = min(min_point[index], position[index] - half)
            max_point[index] = max(max_point[index], position[index] + half)
    if any(value == float("inf") for value in min_point):
        return None
    return min_point, max_point



def _scaled_vector_mm(value: Any, length_factor: float) -> list[float]:
    vector = _vector(value)
    return [item * length_factor for item in vector]


def _normalize_direction(value: list[float]) -> list[float]:
    magnitude = sum(item * item for item in value) ** 0.5
    if magnitude <= 0.0:
        return []
    return [item / magnitude for item in value]


def _round_mm(value: float) -> float:
    rounded = round(value, 6)
    return 0.0 if rounded == -0.0 else rounded


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


def _repair_geometry_components_from_model_ir(
    components: list[dict[str, Any]],
    model_ir: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    ir_components = {
        str(item.get("component_id") or item.get("id") or ""): item
        for item in _as_list(model_ir.get("components"))
        if isinstance(item, dict)
    }
    if not ir_components:
        return components
    length_factor = _model_ir_length_factor(model_ir)
    repaired: list[dict[str, Any]] = []
    for component in components:
        row = dict(component)
        component_id = _text(row.get("id"))
        ir_component = _as_dict(ir_components.get(component_id))
        if _should_repair_cylinder_radius(row, ir_component):
            repaired_size = _cylinder_size_from_ir(ir_component, length_factor)
            if repaired_size:
                row["size_mm"] = repaired_size
                warnings.append(f"geometry_view.json cylinder radius repaired from model IR for {component_id}")
        repaired.append(row)
    return repaired


def _model_ir_length_factor(model_ir: dict[str, Any]) -> float:
    unit_contract = _as_dict(model_ir.get("unit_contract"))
    global_units = _as_dict(model_ir.get("global_units"))
    unit = _text(unit_contract.get("length_unit") or global_units.get("length"), "mm")
    return _length_unit_to_mm_factor(unit)


def _model_ir_coordinate_factor(model_ir: dict[str, Any]) -> float:
    unit_contract = _as_dict(model_ir.get("unit_contract"))
    coordinate_system = _as_dict(model_ir.get("coordinate_system"))
    global_units = _as_dict(model_ir.get("global_units"))
    unit = _text(
        unit_contract.get("coordinate_unit")
        or coordinate_system.get("unit")
        or unit_contract.get("length_unit")
        or global_units.get("length"),
        "mm",
    )
    return _length_unit_to_mm_factor(unit)


def _length_unit_to_mm_factor(unit: str) -> float:
    normalized = unit.strip().lower().replace("µ", "u")
    if normalized in {"um", "micrometer", "micrometers", "micron", "microns"}:
        return 0.001
    if normalized in {"cm", "centimeter", "centimeters"}:
        return 10.0
    if normalized in {"m", "meter", "meters"}:
        return 1000.0
    return 1.0


def _should_repair_cylinder_radius(component: dict[str, Any], ir_component: dict[str, Any]) -> bool:
    shape = _text(component.get("shape") or component.get("geometry_type")).lower()
    ir_shape = _text(ir_component.get("geometry_type") or ir_component.get("shape")).lower()
    if "cylinder" not in shape and "tube" not in shape and "cylinder" not in ir_shape and "tube" not in ir_shape:
        return False
    size = component.get("size_mm")
    if not isinstance(size, list) or len(size) < 3:
        return False
    radius_value = _ir_radius_value(_as_dict(ir_component.get("dimensions")))
    if radius_value is None:
        return False
    radial_size = max(_float(size[0], 0.0), _float(size[1], 0.0))
    return radial_size <= 1.01


def _cylinder_size_from_ir(ir_component: dict[str, Any], length_factor: float) -> list[float]:
    dimensions = _as_dict(ir_component.get("dimensions"))
    radius = _ir_radius_value(dimensions)
    if radius is None:
        return []
    height = dimensions.get("dz")
    if height is None:
        height = dimensions.get("height")
    if height is None:
        height = dimensions.get("z")
    diameter_mm = float(radius) * 2.0 * length_factor
    height_mm = _float(height, 1.0) * length_factor
    return [diameter_mm, diameter_mm, height_mm]


def _ir_radius_value(dimensions: dict[str, Any]) -> float | None:
    for key in ("rmax", "radius", "r"):
        if dimensions.get(key) is None:
            continue
        try:
            return float(dimensions[key])
        except (TypeError, ValueError):
            return None
    return None


def _normalize_ir_component(
    value: Any,
    *,
    length_factor: float = 1.0,
    coordinate_factor: float = 1.0,
) -> dict[str, Any]:
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
        "size_mm": _dimension_size(dimensions, length_factor),
        "position_mm": _scaled_vector_mm(placement.get("position") or row.get("position"), coordinate_factor),
        "rotation_deg": _vector(placement.get("rotation") or row.get("rotation")),
        "color": "",
        "opacity": 0.22 if component_id.lower() == "world" else 0.42,
    }


def _dimension_size(dimensions: dict[str, Any], factor: float = 1.0) -> list[float]:
    radius = _ir_radius_value(dimensions)
    if radius is not None:
        height = dimensions.get("dz")
        if height is None:
            height = dimensions.get("height")
        if height is None:
            height = dimensions.get("z")
        diameter = radius * 2.0 * factor
        return [diameter, diameter, _float(height, 1.0) * factor]
    return [
        _dimension_axis(dimensions, "x", factor),
        _dimension_axis(dimensions, "y", factor),
        _dimension_axis(dimensions, "z", factor),
    ]


def _dimension_axis(dimensions: dict[str, Any], axis: str, factor: float = 1.0) -> float:
    if f"d{axis}" in dimensions:
        return _float(dimensions.get(f"d{axis}"), 1.0) * factor
    if f"half_{axis}" in dimensions:
        return _float(dimensions.get(f"half_{axis}"), 0.5) * 2.0 * factor
    if axis in dimensions:
        return _float(dimensions.get(axis), 1.0) * factor
    return 1.0 * factor


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
