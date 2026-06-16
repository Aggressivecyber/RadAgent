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
    "mosfet",
    "nmos",
    "pmos",
    "finfet",
    "晶体管",
    "阈值",
    "阈值漂移",
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
_PARTICLE_KEYWORDS: tuple[tuple[tuple[str, ...], dict[str, Any]], ...] = (
    (("neutron", "neutrons", "中子"), {"type": "neutron", "pdg_code": 2112}),
    (("muon", "muons", "缪子"), {"type": "mu-", "pdg_code": 13}),
    (("proton", "protons", "质子"), {"type": "proton", "pdg_code": 2212}),
    (("gamma", "gammas", "γ", "伽马"), {"type": "gamma", "pdg_code": 22}),
    (("electron", "electrons", "e-", "电子"), {"type": "electron", "pdg_code": 11}),
)
_OUTPUT_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("edep_3d", "energy deposition map"), "energy_deposition_map"),
    (("total energy deposition", "energy deposition", "edep"), "energy_deposition"),
    (("dose_3d", "dose map", "dose distribution", "detector dose", "dose"), "dose_distribution"),
    (("leakage", "flux", "fluence"), "particle_flux"),
    (("spectrum", "histogram"), "energy_spectrum"),
    (("event_table", "per event", "event data"), "event_data"),
    (("hit", "hits"), "hit_data"),
)

_DEVICE_TID_KEYWORDS = (
    "mosfet",
    "nmos",
    "pmos",
    "finfet",
    "晶体管",
)
_TID_KEYWORDS = ("tid", "total ionizing dose", "总剂量", "阈值漂移")
_EXPLICIT_GEANT4_DOSIMETRY_MARKERS = (
    "geant4",
    "g4",
    "energy deposition",
    "edep",
    "dose",
    "剂量沉积",
    "能量沉积",
)
_MOSFET_TID_MISSING = [
    "MOSFET geometry and dimensions",
    "gate oxide thickness and material stack",
    "radiation source particle, energy or spectrum, and fluence or dose",
    "TID observable: oxide dose only or electrical response such as threshold shift",
    "whether to run Geant4 dose scoring, TCAD device simulation, or a coupled workflow",
]


def detect_scope(query: str) -> list[str]:
    """Detect simulation scope from user query using keyword matching.

    Returns a deduplicated list of scope strings.
    Default is ["geant4"] if no keywords match.
    """
    q = query.lower()
    scope: list[str] = []

    if _is_ambiguous_device_tid_request(q):
        return ["tcad"]

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
    if _is_ambiguous_device_tid_request(query_lower):
        clarification = _device_tid_clarification_request()
        task_spec = {
            "job_id": job_id,
            "user_query": user_query,
            "simulation_scope": scope,
            "modeling_mode": "realistic",
            "metadata": {
                "clarification_required": "true",
                "clarification_reason": clarification["reason"],
            },
            "clarification_request": clarification,
        }
        return {
            "task_spec": task_spec,
            "task_spec_errors": [
                "MOSFET/TID request needs user clarification before code generation."
            ],
            "simulation_scope": scope,
            "clarification_request": clarification,
            "task_planning_status": "needs_user_input",
            "termination_reason": clarification["message"],
            "current_node": "parse_task",
        }

    energy_value, energy_unit = _parse_energy(user_query)
    events = _parse_events(user_query)
    target = _parse_target(user_query)
    outputs = _parse_outputs(user_query)
    metadata: dict[str, str] = {}
    model_plan: dict[str, Any] = {}

    # Parse particle info. Use explicit transport particle mentions before
    # secondary products so a neutron shielding task is not misclassified as
    # gamma just because it asks for secondary-gamma scoring.
    particle = _detect_particle(query_lower)
    if not particle:
        model_plan = await _model_assisted_task_plan(user_query, job_id)
        particle = _normalize_model_particle(
            model_plan.get("particle"),
            fallback_energy=energy_value,
            fallback_unit=energy_unit,
        )
        outputs = _merge_outputs(outputs, _normalize_model_outputs(model_plan.get("outputs")))
        if not target:
            target = _normalize_model_target(model_plan.get("target"))
        if model_plan:
            metadata["model_assisted_task_planning"] = "true"

    if particle:
        particle = {
            **particle,
            "energy_MeV": particle.get("energy_MeV", energy_value),
            "energy_unit": particle.get("energy_unit", energy_unit),
            "energy_distribution": particle.get("energy_distribution", "mono"),
            "direction": particle.get("direction", [0.0, 0.0, 1.0]),
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


def _detect_particle(query_lower: str) -> dict[str, Any]:
    for keywords, particle in _PARTICLE_KEYWORDS:
        if any(keyword in query_lower for keyword in keywords):
            result = dict(particle)
            if result["type"] == "mu-" and "cosmic" in query_lower:
                result["angular_distribution"] = "cosine"
                result["generator_type"] = "gps"
                result["direction"] = [0.0, 0.0, -1.0]
            return result
    return {}


async def _model_assisted_task_plan(user_query: str, job_id: str) -> dict[str, Any]:
    """Ask the model for structured planning only when rules are insufficient."""
    try:
        from agent_core.models.gateway import get_model_gateway
        from agent_core.models.schemas import ModelTask, ModelTier

        gateway = get_model_gateway()
        result = await gateway.call(
            task=ModelTask.TASK_PLANNING,
            tier=ModelTier.PRO,
            system_prompt=(
                "Extract simulation planning facts as JSON. Never invent a particle, "
                "energy, geometry, material, or source when the user did not provide "
                "one. Return JSON with optional keys particle, target, outputs, "
                "missing, ask_user, assumptions. Use particle only when the request "
                "explicitly states a transport particle or enough source context. "
                "outputs must be stable snake_case names such as energy_deposition, "
                "dose_distribution, particle_flux, hit_data, energy_spectrum, "
                "event_data."
            ),
            user_prompt=user_query,
            response_format="json",
            temperature=0.0,
            max_tokens=900,
            metadata={
                "job_id": job_id,
                "module_name": "task_planning_model_assist",
            },
        )
        data = result.parsed_json
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _is_ambiguous_device_tid_request(query_lower: str) -> bool:
    has_device = any(keyword in query_lower for keyword in _DEVICE_TID_KEYWORDS)
    has_tid = any(keyword in query_lower for keyword in _TID_KEYWORDS)
    has_geant4_dose_only = (
        ("geant4" in query_lower or "g4" in query_lower)
        and any(marker in query_lower for marker in _EXPLICIT_GEANT4_DOSIMETRY_MARKERS)
        and not any(marker in query_lower for marker in ("阈值", "threshold", "电学"))
    )
    return has_device and has_tid and not has_geant4_dose_only


def _device_tid_clarification_request() -> dict[str, Any]:
    return {
        "reason": "ambiguous_device_tid",
        "message": (
            "MOSFET TID can mean Geant4 oxide-dose scoring, TCAD electrical "
            "response, or a coupled workflow. The workflow needs clarification "
            "before generating code."
        ),
        "missing_information": list(_MOSFET_TID_MISSING),
        "questions": [
            {
                "id": "workflow_scope",
                "question": (
                    "Should this run Geant4 dose scoring only, TCAD electrical "
                    "response, or a coupled Geant4-to-TCAD workflow?"
                ),
            },
            {
                "id": "source_definition",
                "question": (
                    "What radiation source should be used: particle type, energy "
                    "or spectrum, fluence or dose, and incidence geometry?"
                ),
            },
            {
                "id": "device_geometry",
                "question": (
                    "What MOSFET structure should be modeled: oxide thickness, "
                    "channel dimensions, material stack, doping, contacts, and bias?"
                ),
            },
        ],
    }


def _normalize_model_particle(
    value: Any,
    *,
    fallback_energy: float,
    fallback_unit: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    particle_type = str(value.get("type") or "").strip()
    if not particle_type:
        return {}
    unit = _canonical_energy_unit(str(value.get("energy_unit") or fallback_unit))
    energy = _optional_positive_float(value.get("energy_MeV"), fallback_energy)
    particle: dict[str, Any] = {
        "type": particle_type,
        "energy_MeV": energy,
        "energy_unit": unit,
        "energy_distribution": str(value.get("energy_distribution") or "mono"),
        "direction": _normal_direction(value.get("direction")),
    }
    pdg = _optional_int(value.get("pdg_code"))
    if pdg is not None:
        particle["pdg_code"] = pdg
    angular = str(value.get("angular_distribution") or "").strip()
    if angular in {"mono", "gaussian", "isotropic", "cosine", "custom"}:
        particle["angular_distribution"] = angular
    generator = str(value.get("generator_type") or "").strip()
    if generator in {"gun", "gps"}:
        particle["generator_type"] = generator
    return particle


def _normalize_model_outputs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    outputs: list[str] = []
    for item in value:
        text = str(item or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text and text not in outputs:
            outputs.append(text)
    return outputs


def _merge_outputs(base: list[str], extra: list[str]) -> list[str]:
    result = list(base)
    for output in extra:
        if output not in result:
            result.append(output)
    return result


def _normalize_model_target(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    material = str(value.get("material") or "").strip()
    if not material:
        return None
    target: dict[str, Any] = {
        "material": material,
        "geometry_type": str(value.get("geometry_type") or "box"),
    }
    size = value.get("size_um")
    if isinstance(size, list) and len(size) == 3:
        parsed = [_optional_positive_float(item, 0.0) for item in size]
        if all(item > 0 for item in parsed):
            target["size_um"] = parsed
    return target


def _optional_positive_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normal_direction(value: Any) -> list[float]:
    if isinstance(value, list) and len(value) == 3:
        try:
            parsed = [float(item) for item in value]
        except (TypeError, ValueError):
            return [0.0, 0.0, 1.0]
        if any(item != 0.0 for item in parsed):
            return parsed
    return [0.0, 0.0, 1.0]


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
    if state.get("task_planning_status") == "needs_user_input" or task_spec.get(
        "clarification_request"
    ):
        return {
            "task_spec_errors": errors,
            "task_planning_status": "needs_user_input",
            "clarification_request": task_spec.get(
                "clarification_request", state.get("clarification_request", {})
            ),
            "termination_reason": state.get("termination_reason", ""),
        }

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
        "task_spec_errors": list(state.get("task_spec_errors", [])),
        "task_planning_status": state.get("task_planning_status", ""),
        "clarification_request": state.get("clarification_request", {}),
        "termination_reason": state.get("termination_reason", ""),
    }
