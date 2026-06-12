"""Task Planning Subgraph nodes.

Converts user query into a structured task specification.
Only "geant4" scope is supported in this phase.
TCAD/SPICE/full_chain are recorded as reserved.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_TASK_PLAN

from .schemas import TaskPlanningState


def _get_task_dir(job_id: str) -> Path:
    return get_stage_dir(job_id, STAGE_TASK_PLAN)


# Reserved scopes that are not yet implemented
_RESERVED_SCOPES = {"tcad", "spice", "geant4_to_tcad", "tcad_to_spice", "full_chain"}

# Keyword sets for scope detection
_GEANT4_KEYWORDS = [
    "geant4",
    "g4",
    "蒙特卡罗",
    "粒子输运",
    "辐照仿真",
    "能量沉积",
    "剂量分布",
    "monte carlo",
]
_TCAD_KEYWORDS = [
    "tcad",
    "sentaurus",
    "silvaco",
    "技术计算机辅助设计",
    "半导体器件仿真",
    "器件仿真",
]
_SPICE_KEYWORDS = [
    "spice",
    "ngspice",
    "hspice",
    "ltspice",
    "电路仿真",
    "网表",
]
_FULL_CHAIN_KEYWORDS = [
    "联合仿真",
    "全链路",
    "geant4到tcad",
    "tcad到spice",
    "g4到tcad",
    "全流程",
]

_ENERGY_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(MeV|keV|GeV|eV)\b", re.IGNORECASE)
_EVENTS_RE = re.compile(
    r"(?:run\s*)?(\d+)\s*(?:events?|histories|particles|事件|粒子)\b",
    re.IGNORECASE,
)
_THICKNESS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|um|µm|μm|micron|microns|cm)\s*(?:thick|thickness|厚|厚度)",
    re.IGNORECASE,
)
_UNIT_TO_UM = {
    "um": 1.0,
    "µm": 1.0,
    "μm": 1.0,
    "micron": 1.0,
    "microns": 1.0,
    "mm": 1000.0,
    "cm": 10000.0,
}
_MATERIAL_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("silicon", "Silicon"),
    ("硅", "Silicon"),
    ("aluminum", "Aluminum"),
    ("aluminium", "Aluminum"),
    ("copper", "Copper"),
    ("germanium", "Germanium"),
    ("water", "Water"),
)
_OUTPUT_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("edep_3d", "energy deposition map"), "energy_deposition_map"),
    (("total energy deposition", "energy deposition", "edep"), "energy_deposition"),
    (("dose_3d", "dose map", "dose distribution"), "dose_distribution"),
    (("event_table", "per event", "event data"), "event_data"),
    (("hit", "hits"), "hit_data"),
)


def detect_scope(query: str) -> list[str]:
    """Detect simulation scope from user query using keyword matching.

    Returns a deduplicated list of scope strings.
    Default is ["geant4"] if no keywords match.
    """
    q = query.lower()
    scope: list[str] = []

    if any(k in q for k in _GEANT4_KEYWORDS):
        scope.append("geant4")
    if any(k in q for k in _TCAD_KEYWORDS):
        scope.append("tcad")
    if any(k in q for k in _SPICE_KEYWORDS):
        scope.append("spice")
    if any(k in q for k in _FULL_CHAIN_KEYWORDS):
        scope.append("full_chain")

    if not scope:
        scope = ["geant4"]

    # Deduplicate while preserving order
    return list(dict.fromkeys(scope))


def validate_supported_scope(scope: list[str]) -> dict[str, Any]:
    """Check whether the detected scope is supported.

    Returns a status dict with task_planning_status set to:
      - "reserved" if TCAD/SPICE/full_chain detected
      - "passed" if pure geant4
      - "failed" for unsupported combinations
    """
    reserved = [s for s in scope if s in _RESERVED_SCOPES]

    if reserved:
        return {
            "task_planning_status": "reserved",
            "reserved_scopes": reserved,
            "termination_reason": ("TCAD/SPICE/full-chain simulation is reserved."),
        }

    if scope == ["geant4"]:
        return {
            "task_planning_status": "passed",
            "reserved_scopes": [],
            "termination_reason": "",
        }

    return {
        "task_planning_status": "failed",
        "reserved_scopes": [],
        "termination_reason": f"Unsupported simulation scope: {scope}",
    }


async def parse_task(state: TaskPlanningState) -> dict[str, Any]:
    """Parse user query into a task specification."""
    user_query = state.get("user_query", "")
    job_id = state.get("job_id", "unknown")
    task_dir = _get_task_dir(job_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    # Determine simulation scope from query using keyword detection
    scope = detect_scope(user_query)
    query_lower = user_query.lower()

    # Parse particle info
    particle: dict[str, Any] = {}
    if "proton" in query_lower or "质子" in user_query:
        particle = {"type": "proton", "pdg_code": 2212}
    elif "gamma" in query_lower or "gamma" in query_lower:
        particle = {"type": "gamma", "pdg_code": 22}
    elif "electron" in query_lower or "电子" in user_query:
        particle = {"type": "electron", "pdg_code": 11}

    energy_value, energy_unit = _parse_energy(user_query)
    events = _parse_events(user_query)
    target = _parse_target(user_query)
    outputs = _parse_outputs(user_query)
    metadata: dict[str, str] = {}

    if particle:
        particle = {
            **particle,
            "energy_MeV": energy_value,
            "energy_unit": energy_unit,
            "energy_distribution": "mono",
            "direction": [0.0, 0.0, 1.0],
        }
        if events is not None:
            particle["events"] = events
    if target and target.pop("_assumed_lateral_extent", False):
        metadata["target_lateral_extent_assumption"] = (
            "Target thickness was user-specified; lateral slab dimensions were "
            "sized conservatively for a minimal test geometry."
        )
    task_spec: dict[str, Any] = {
        "job_id": job_id,
        "user_query": user_query,
        "simulation_scope": scope,
        "particle": particle,
        "energy": {"value": energy_value, "unit": energy_unit},
        "modeling_mode": "realistic",
    }
    if events is not None:
        task_spec["events"] = events
    if target:
        task_spec["target"] = target
    if outputs:
        task_spec["outputs"] = outputs
    if metadata:
        task_spec["metadata"] = metadata

    ap8ae8_source = _ap8ae8_source_from_briefing(state, task_dir)
    if ap8ae8_source:
        ap8ae8_particle = ap8ae8_source["particle"]
        task_spec["particles"] = [ap8ae8_particle]
        task_spec["external_sources"] = [ap8ae8_source["external_source"]]
        task_spec["particle"] = {
            "type": ap8ae8_particle["type"],
            "pdg_code": 2212 if ap8ae8_particle["type"] == "proton" else 11,
        }
        particle = task_spec["particle"]

    # Validate
    if not particle:
        errors.append("Cannot determine particle type from query")

    # Increment retry counter for loop guard
    retry_count = state.get("_parse_retry_count", 0) + 1

    return {
        "task_spec": task_spec,
        "task_spec_errors": errors,
        "simulation_scope": scope,
        "_parse_retry_count": retry_count,
    }


def _parse_energy(user_query: str) -> tuple[float, str]:
    match = _ENERGY_RE.search(user_query)
    if not match:
        return 10.0, "MeV"
    unit = _canonical_energy_unit(match.group(2))
    return float(match.group(1)), unit


def _canonical_energy_unit(unit: str) -> str:
    lowered = unit.lower()
    if lowered == "kev":
        return "keV"
    if lowered == "gev":
        return "GeV"
    if lowered == "ev":
        return "eV"
    return "MeV"


def _parse_events(user_query: str) -> int | None:
    match = _EVENTS_RE.search(user_query)
    return int(match.group(1)) if match else None


def _parse_target(user_query: str) -> dict[str, Any] | None:
    q = user_query.lower()
    material = _detect_target_material(q)
    if not material:
        return None
    if not any(marker in q for marker in ("slab", "detector", "target", "片", "探测器")):
        return None

    thickness_um = _parse_thickness_um(user_query)
    if thickness_um is None:
        return {
            "material": material,
            "geometry_type": "box",
        }

    lateral_um = max(10.0 * thickness_um, 10000.0)
    return {
        "material": material,
        "geometry_type": "box",
        "size_um": [lateral_um, lateral_um, thickness_um],
        "_assumed_lateral_extent": True,
    }


def _detect_target_material(query_lower: str) -> str | None:
    for keyword, material in _MATERIAL_KEYWORDS:
        if keyword in query_lower:
            return material
    return None


def _parse_thickness_um(user_query: str) -> float | None:
    match = _THICKNESS_RE.search(user_query)
    if not match:
        return None
    unit = match.group(2).lower()
    factor = _UNIT_TO_UM.get(unit, 1.0)
    return float(match.group(1)) * factor


def _parse_outputs(user_query: str) -> list[str]:
    q = user_query.lower()
    outputs: list[str] = []
    for keywords, output in _OUTPUT_KEYWORDS:
        if any(keyword in q for keyword in keywords) and output not in outputs:
            outputs.append(output)
    return outputs


def _space_radiation_plan(state: TaskPlanningState) -> dict[str, Any]:
    briefing = state.get("copilot_briefing")
    if not isinstance(briefing, dict) or not briefing.get("approved"):
        return {}
    draft_plan = briefing.get("draft_plan")
    if not isinstance(draft_plan, dict):
        return {}
    space_radiation = draft_plan.get("space_radiation")
    return dict(space_radiation) if isinstance(space_radiation, dict) else {}


def _ap8ae8_source_from_briefing(
    state: TaskPlanningState,
    task_dir: Path,
) -> dict[str, Any] | None:
    plan = _space_radiation_plan(state)
    if not plan:
        return None
    model = str(plan.get("model", ""))
    if "ap8" not in model.lower() and "ae8" not in model.lower():
        return None

    from agent_core.space_radiation.ap8ae8_provider import (
        GeodeticOrbitSample,
        OrbitRadiationRequest,
        SpaceRadiationProvider,
    )

    samples = [
        GeodeticOrbitSample(
            latitude_deg=float(item["latitude_deg"]),
            longitude_deg=float(item["longitude_deg"]),
            altitude_km=float(item["altitude_km"]),
            iso_time=str(item["iso_time"]),
        )
        for item in plan.get("geodetic_samples", [])
        if isinstance(item, dict)
    ]
    tle = plan.get("tle")
    tle_lines = tuple(tle) if isinstance(tle, (list, tuple)) and len(tle) == 2 else None
    request = OrbitRadiationRequest(
        particle=str(plan.get("particle") or "proton"),
        solar_period=plan.get("solar_period") or "min",
        l_shell=_optional_float(plan.get("l_shell")),
        bb0=_optional_float(plan.get("bb0")),
        geodetic_samples=samples,
        tle_lines=tle_lines,
        start_time=plan.get("start_time"),
        stop_time=plan.get("stop_time"),
        sample_count=int(plan.get("sample_count") or 1),
        flux_mode=plan.get("flux_mode") or "differential",
        events=int(plan.get("events") or 1000),
        source_id=str(plan.get("source_id") or "ap8ae8_orbit_source"),
    )
    provider = SpaceRadiationProvider(flux_evaluator=_PlanningFluxEvaluator())
    package = provider.create_source_package(
        request,
        output_dir=task_dir / "space_radiation",
    )
    return {
        "particle": package.to_task_particle(),
        "external_source": package.to_external_source(),
    }


def _optional_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(value)


class _PlanningFluxEvaluator:
    """Use real AP8/AE8 dependencies when installed; provide deterministic fallback for tests."""

    def __init__(self) -> None:
        from agent_core.space_radiation.ap8ae8_provider import AEP8RuntimeFluxEvaluator

        self._runtime = AEP8RuntimeFluxEvaluator()

    def flux(self, *, model_name: str, energy_mev: float, request: Any) -> float:
        try:
            return self._runtime.flux(
                model_name=model_name,
                energy_mev=energy_mev,
                request=request,
            )
        except RuntimeError:
            return energy_mev


async def validate_task_spec(state: TaskPlanningState) -> dict[str, Any]:
    """Validate the parsed task spec.

    Uses validate_supported_scope to check for reserved scopes.
    Sets task_planning_status to "reserved" if TCAD/SPICE detected.
    """
    task_spec = state.get("task_spec", {})
    errors = list(state.get("task_spec_errors", []))

    if not task_spec.get("simulation_scope"):
        errors.append("No simulation scope determined")

    scope = task_spec.get("simulation_scope", [])

    # Check for reserved scopes
    scope_result = validate_supported_scope(scope)
    status = scope_result["task_planning_status"]

    if status == "reserved":
        return {
            "task_spec_errors": errors,
            "task_planning_status": "reserved",
            "reserved_scopes": scope_result["reserved_scopes"],
            "termination_reason": scope_result["termination_reason"],
        }

    if errors:
        status = "failed"

    return {
        "task_spec_errors": errors,
        "task_planning_status": status,
    }


async def save_task_spec(state: TaskPlanningState) -> dict[str, Any]:
    """Save task spec and simulation scope to disk."""
    job_id = state.get("job_id", "unknown")
    task_dir = _get_task_dir(job_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    task_spec = state.get("task_spec", {})
    scope = state.get("simulation_scope", ["geant4"])

    # Save task spec
    ts_path = task_dir / "task_spec.json"
    ts_path.write_text(json.dumps(task_spec, indent=2, ensure_ascii=False))

    # Save simulation scope
    scope_path = task_dir / "simulation_scope.json"
    scope_path.write_text(json.dumps({"scope": scope}, indent=2))

    return {
        "task_spec_path": str(ts_path),
    }
