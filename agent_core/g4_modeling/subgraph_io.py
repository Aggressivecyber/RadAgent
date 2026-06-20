"""G4 Modeling Subgraph — I/O adapters.

Bridges between the subgraph state and existing nodes:
- Loads task_spec from file before passing to nodes
- Persists g4_model_ir to disk after each node
- Extracts output paths for the main graph
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_MODEL_IR

from .subgraph_state import G4ModelingSubgraphState


async def load_task_spec(state: G4ModelingSubgraphState) -> dict[str, Any]:
    """Load task spec from file path into state for node consumption."""
    task_spec_path = state.get("task_spec_path", "")
    if task_spec_path and Path(task_spec_path).exists():
        task_spec = json.loads(Path(task_spec_path).read_text())
    else:
        task_spec = {}
    confirmed_plan_path = state.get("confirmed_requirement_plan_path", "")
    confirmed_plan = {}
    if confirmed_plan_path and Path(confirmed_plan_path).exists():
        confirmed_plan = json.loads(Path(confirmed_plan_path).read_text())
    if confirmed_plan:
        task_spec = dict(task_spec)
        metadata = dict(task_spec.get("metadata", {}))
        metadata["confirmed_requirement_plan_path"] = confirmed_plan_path
        task_spec["metadata"] = metadata
        task_spec["confirmed_requirement_plan"] = confirmed_plan
        task_spec = apply_confirmed_requirement_plan(task_spec, confirmed_plan)

    return {
        "task_spec": task_spec,
        "confirmed_requirement_plan": confirmed_plan,
        "modeling_mode": "realistic",
        "retry_count": 0,
        "errors": [],
    }


async def persist_model_ir(state: G4ModelingSubgraphState) -> dict[str, Any]:
    """Persist the g4_model_ir to disk and generate all output paths."""
    job_id = state.get("job_id", "unknown")
    model_ir_dict = state.get("g4_model_ir", {})

    if not model_ir_dict:
        return {
            "g4_modeling_status": "failed",
            "errors": ["No g4_model_ir generated"],
        }

    model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
    model_ir_dir.mkdir(parents=True, exist_ok=True)

    # Save main IR
    ir_path = model_ir_dir / "g4_model_ir.json"
    ir_path.write_text(json.dumps(model_ir_dict, indent=2, ensure_ascii=False))

    # Save component specs
    specs_dir = model_ir_dir / "component_specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    components = model_ir_dict.get("components", [])
    for comp in components:
        comp_id = comp.get("component_id", "unknown")
        spec_path = specs_dir / f"{comp_id}.json"
        spec_path.write_text(json.dumps(comp, indent=2, ensure_ascii=False))

    # Save interfaces
    interfaces = model_ir_dict.get("interfaces", [])
    interfaces_path = model_ir_dir / "interfaces.json"
    interfaces_path.write_text(json.dumps(interfaces, indent=2, ensure_ascii=False))

    # Save material spec
    materials = model_ir_dict.get("materials", [])
    mat_path = model_ir_dir / "material_spec.json"
    mat_path.write_text(json.dumps(materials, indent=2, ensure_ascii=False))

    # Save source spec
    sources = model_ir_dict.get("sources", [])
    src_path = model_ir_dir / "source_spec.json"
    src_path.write_text(json.dumps(sources, indent=2, ensure_ascii=False))

    # Save physics spec
    physics = model_ir_dict.get("physics", {})
    phys_path = model_ir_dir / "physics_spec.json"
    phys_path.write_text(json.dumps(physics, indent=2, ensure_ascii=False))

    # Save scoring spec
    scoring = model_ir_dict.get("scoring", [])
    score_path = model_ir_dir / "scoring_spec.json"
    score_path.write_text(json.dumps(scoring, indent=2, ensure_ascii=False))

    # Save sensitive detector spec
    sds = model_ir_dict.get("sensitive_detectors", [])
    sd_path = model_ir_dir / "sensitive_detector_spec.json"
    sd_path.write_text(json.dumps(sds, indent=2, ensure_ascii=False))

    # Save construction ledger
    ledger = model_ir_dict.get("ledger", {})
    ledger_path = model_ir_dir / "construction_ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False))

    # Save model review report
    review_report = state.get("model_review_report", "")
    review_path = model_ir_dir / "model_review_report.md"
    default_review = "# Model Review\n\nNo review generated.\n"
    review_path.write_text(review_report if review_report else default_review)

    human_confirmation_required = _requires_human_confirmation(model_ir_dict)

    # Determine status
    errors = state.get("model_ir_errors", [])
    status = "passed" if not errors else "failed"

    return {
        "g4_model_ir_path": str(ir_path),
        "component_specs_dir": str(specs_dir),
        "interfaces_path": str(interfaces_path),
        "construction_ledger_path": str(ledger_path),
        "model_review_report_path": str(review_path),
        "g4_modeling_status": status,
        "human_confirmation_required": human_confirmation_required,
    }


def _requires_human_confirmation(model_ir: dict[str, Any]) -> bool:
    """Return whether the persisted IR has unresolved user-confirmation items."""
    if model_ir.get("unconfirmed_fields"):
        return True
    if model_ir.get("open_issues"):
        return True

    sections = (
        "components",
        "materials",
        "sources",
        "scoring",
        "sensitive_detectors",
    )
    for section in sections:
        items = model_ir.get(section, [])
        if not isinstance(items, list):
            continue
        if any(_item_needs_confirmation(item) for item in items):
            return True

    physics = model_ir.get("physics")
    return isinstance(physics, dict) and _item_needs_confirmation(physics)


def _item_needs_confirmation(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("open_issues"):
        return True
    return bool(item.get("requires_confirmation")) and not bool(item.get("confirmed_by_user"))


def apply_confirmed_requirement_plan(
    task_spec: dict[str, Any],
    confirmed_plan: dict[str, Any],
) -> dict[str, Any]:
    """Project approved review fields into the structured task spec."""
    if not isinstance(task_spec, dict) or not isinstance(confirmed_plan, dict):
        return task_spec
    if confirmed_plan.get("approval_status") not in {"approved", "pass", "passed", None}:
        return task_spec

    normalized = dict(task_spec)
    parameters = _confirmed_parameters(confirmed_plan)
    if not parameters:
        if normalized.get("particle") == {}:
            normalized.pop("particle", None)
        return normalized

    events = _event_count_from_parameters(parameters)
    if events is not None:
        normalized["events"] = events

    outputs = _outputs_from_parameters(parameters)
    if outputs:
        normalized["outputs"] = outputs

    physics_list = _physics_list_from_parameters(parameters)
    if physics_list:
        physics_options = dict(normalized.get("physics_options") or {})
        physics_options["physics_list"] = physics_list
        normalized["physics_options"] = physics_options

    particles = _particles_from_parameters(parameters, normalized)
    if particles:
        normalized["particles"] = particles
        normalized.pop("particle", None)
    elif normalized.get("particle") == {}:
        normalized.pop("particle", None)

    target = _target_from_parameters(parameters, normalized.get("target"))
    if target:
        normalized["target"] = target

    metadata = dict(normalized.get("metadata") or {})
    metadata["confirmed_requirement_fields"] = ",".join(sorted(parameters))
    normalized["metadata"] = metadata
    return normalized


def _confirmed_parameters(confirmed_plan: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    review = confirmed_plan.get("review")
    if isinstance(review, dict):
        for item in _dict_list(review.get("proposed_parameters")):
            field_path = str(item.get("field_path") or "").strip()
            if not field_path:
                continue
            value = item.get("proposed_value")
            if value in (None, ""):
                value = item.get("selected_value")
            if value not in (None, ""):
                params[field_path] = value
        for item in _dict_list(review.get("confirmed_requirement_answers")):
            field_path = str(item.get("field_path") or "").strip()
            if not field_path:
                continue
            value = item.get("selected_value")
            if value in (None, ""):
                value = item.get("recommended_value")
            if value not in (None, ""):
                params[field_path] = value

    response = confirmed_plan.get("user_response")
    if isinstance(response, dict):
        for supplement in _dict_list(response.get("requirements_review_supplements")):
            feedback = str(supplement.get("feedback") or "")
            params.update(_parameters_from_feedback_text(feedback))
    return params


def _parameters_from_feedback_text(text: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("RADAGENT_CONFIRMATION_JSON:"):
            continue
        match = re.match(r"^([^:\n]{1,180})\s*:\s*(?:确认推荐|修改为)\s+(.+)$", stripped)
        if not match:
            continue
        params[match.group(1).strip()] = match.group(2).strip()
    return params


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _event_count_from_parameters(parameters: dict[str, Any]) -> int | None:
    for key in ("run.event_count", "source.events", "events"):
        if key not in parameters:
            continue
        match = re.search(r"\d+", str(parameters[key]))
        if match:
            return max(1, int(match.group(0)))
    return None


def _outputs_from_parameters(parameters: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(parameters[key])
        for key in parameters
        if key.startswith("scoring.") or key.startswith("output")
    ).lower()
    outputs: list[str] = []
    if any(token in text for token in ("energy deposition", "能量沉积", "edep", "mev")):
        outputs.append("energy_deposition")
    if any(token in text for token in ("dose", "剂量", "gy")):
        outputs.append("dose_distribution")
    if any(token in text for token in ("event", "事件", "track", "逐粒子")):
        outputs.append("event_data")
    elif outputs:
        outputs.append("event_data")
    return list(dict.fromkeys(outputs))


def _physics_list_from_parameters(parameters: dict[str, Any]) -> str | None:
    raw = parameters.get("physics_list") or parameters.get("physics.physics_list")
    if raw is None:
        return None
    text = str(raw)
    known = ("QGSP_BIC_HP", "QGSP_BERT", "FTFP_BERT", "QGSP_BIC", "Shielding")
    for name in known:
        if name in text:
            return name
    return text.strip() or None


def _particles_from_parameters(
    parameters: dict[str, Any],
    task_spec: dict[str, Any],
) -> list[dict[str, Any]]:
    source_text = " ".join(
        str(value)
        for key, value in parameters.items()
        if key.startswith("source.")
    )
    if not source_text:
        return []

    direction = _direction_from_text(source_text)
    position = _position_from_text(source_text, direction)
    radius_um = _beam_radius_um(source_text)
    events = _event_count_from_parameters(parameters) or task_spec.get("events") or 1000
    geometry: dict[str, Any] = {}
    if radius_um is not None:
        geometry = {
            "surface_shape": "circle",
            "surface_size": [radius_um],
            "generator_type": "gps",
        }
    mixture_text = str(parameters.get("source.particle_mixture") or "").strip()
    if mixture_text:
        particle_text = " ".join([mixture_text, str(parameters.get("source.energy") or "")])
    else:
        particle_text = " ".join(
            [
                _primary_source_choice_text(parameters.get("source.particle")),
                str(parameters.get("source.energy") or ""),
            ]
        ).strip()
    particle_text = particle_text or source_text

    specs: list[dict[str, Any]] = []
    if _mentions_neutron(particle_text):
        specs.append(
            _particle_spec(
                source_id="primary_neutron",
                particle_type="neutron",
                energy=_energy_for_particle(particle_text, "neutron", 14.1),
                direction=direction,
                position=position,
                events=events,
                relative_weight=0.5 if _mentions_gamma(particle_text) else None,
                source_evidence=["confirmed_requirement_plan:source.particle_mixture"],
                geometry=geometry,
            )
        )
    if _mentions_gamma(particle_text):
        specs.append(
            _particle_spec(
                source_id="primary_gamma",
                particle_type="gamma",
                energy=_energy_for_particle(particle_text, "gamma", _default_energy(task_spec)),
                direction=direction,
                position=position,
                events=events,
                relative_weight=0.5 if _mentions_neutron(particle_text) else None,
                source_evidence=["confirmed_requirement_plan:source.particle"],
                geometry=geometry,
            )
        )
    if not specs:
        particle_type = _particle_type_from_text(particle_text)
        if particle_type:
            specs.append(
                _particle_spec(
                    source_id=f"primary_{particle_type}",
                    particle_type=particle_type,
                    energy=_energy_for_particle(
                        particle_text,
                        particle_type,
                        _default_energy(task_spec),
                    ),
                    direction=direction,
                    position=position,
                    events=events,
                    relative_weight=None,
                    source_evidence=["confirmed_requirement_plan:source.particle"],
                    geometry=geometry,
                )
            )
    return specs


def _particle_spec(
    *,
    source_id: str,
    particle_type: str,
    energy: float,
    direction: list[float],
    position: list[float],
    events: int,
    relative_weight: float | None,
    source_evidence: list[str],
    geometry: dict[str, Any],
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "source_id": source_id,
        "type": particle_type,
        "energy_MeV": energy,
        "energy_unit": "MeV",
        "energy_distribution": "mono",
        "direction": direction,
        "position": position,
        "events": events,
        "source_evidence": source_evidence,
    }
    if relative_weight is not None:
        spec["relative_weight"] = relative_weight
    spec.update(geometry)
    return spec


def _mentions_neutron(text: str) -> bool:
    lowered = text.lower()
    return "neutron" in lowered or "中子" in text


def _mentions_gamma(text: str) -> bool:
    lowered = text.lower()
    return "gamma" in lowered or "photon" in lowered or "光子" in text


def _particle_type_from_text(text: str) -> str | None:
    lowered = text.lower()
    for particle_type, aliases in {
        "proton": ("proton", "质子"),
        "electron": ("electron", "e-", "电子"),
        "gamma": ("gamma", "photon", "光子"),
        "neutron": ("neutron", "中子"),
    }.items():
        if any(alias in lowered or alias in text for alias in aliases):
            return particle_type
    return None


def _primary_source_choice_text(value: Any) -> str:
    """Drop optional alternatives from a single-particle review answer."""
    text = str(value or "").strip()
    if not text:
        return ""
    if not re.search(r"若需|可选|optional|更真实", text, flags=re.IGNORECASE):
        return text
    if re.match(
        r"^\s*(gamma|photon|proton|electron|neutron|光子|质子|电子|中子)\s*[（(]",
        text,
        flags=re.IGNORECASE,
    ):
        return re.split(r"[（(]", text, maxsplit=1)[0].strip()
    return text


def _energy_for_particle(text: str, particle_type: str, default: float) -> float:
    spans = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(MeV|keV|GeV|eV)?", text, flags=re.IGNORECASE))
    if not spans:
        return default
    lowered = text.lower()
    aliases = {
        "neutron": ("neutron", "中子"),
        "gamma": ("gamma", "photon", "光子"),
        "proton": ("proton", "质子"),
        "electron": ("electron", "电子"),
    }.get(particle_type, (particle_type,))
    alias_pattern = "|".join(re.escape(alias) for alias in aliases)
    energy_before_particle = re.search(
        rf"(\d+(?:\.\d+)?)\s*(MeV|keV|GeV|eV)?\s*(?:{alias_pattern})",
        lowered,
        flags=re.IGNORECASE,
    )
    if energy_before_particle:
        return _energy_to_mev(
            float(energy_before_particle.group(1)),
            energy_before_particle.group(2) or "MeV",
        )
    particle_before_energy = re.search(
        rf"(?:{alias_pattern})[^\d]{{0,24}}(\d+(?:\.\d+)?)\s*(MeV|keV|GeV|eV)?",
        lowered,
        flags=re.IGNORECASE,
    )
    if particle_before_energy:
        return _energy_to_mev(
            float(particle_before_energy.group(1)),
            particle_before_energy.group(2) or "MeV",
        )
    candidates: list[tuple[int, re.Match[str]]] = []
    for match in spans:
        start = max(0, match.start() - 24)
        end = min(len(lowered), match.end() + 24)
        window = lowered[start:end]
        distances = [
            abs((start + window.index(alias)) - match.start())
            for alias in aliases
            if alias in window
        ]
        if distances:
            candidates.append((min(distances), match))
    if candidates:
        _, match = min(candidates, key=lambda item: item[0])
        return _energy_to_mev(float(match.group(1)), match.group(2) or "MeV")
    return _energy_to_mev(float(spans[0].group(1)), spans[0].group(2) or "MeV")


def _energy_to_mev(value: float, unit: str) -> float:
    unit_lower = unit.lower()
    if unit_lower == "gev":
        return value * 1000.0
    if unit_lower == "kev":
        return value / 1000.0
    if unit_lower == "ev":
        return value / 1_000_000.0
    return value


def _default_energy(task_spec: dict[str, Any]) -> float:
    energy = task_spec.get("energy")
    if isinstance(energy, dict):
        value = energy.get("value")
        unit = str(energy.get("unit") or "MeV")
        if value is not None:
            try:
                return _energy_to_mev(float(value), unit)
            except (TypeError, ValueError):
                pass
    return 10.0


def _direction_from_text(text: str) -> list[float]:
    lowered = text.lower()
    if "-z" in lowered or "沿-z" in lowered or "负z" in lowered:
        return [0.0, 0.0, -1.0]
    if "+z" in lowered or "沿+z" in lowered or "正z" in lowered:
        return [0.0, 0.0, 1.0]
    if "上方" in text or "from above" in lowered:
        return [0.0, 0.0, -1.0]
    return [0.0, 0.0, 1.0]


def _position_from_text(text: str, direction: list[float]) -> list[float]:
    distance_um = _distance_um(text) or 0.0
    if distance_um <= 0:
        return [0.0, 0.0, 0.0]
    return [
        -direction[0] * distance_um,
        -direction[1] * distance_um,
        -direction[2] * distance_um,
    ]


def _beam_radius_um(text: str) -> float | None:
    unit_pattern = r"cm|mm|um|µm|m|米|厘米|毫米|微米"
    pattern = rf"(?:束半径|beam radius|半径)\s*(\d+(?:\.\d+)?)\s*({unit_pattern})"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        pattern = rf"(\d+(?:\.\d+)?)\s*({unit_pattern})\s*(?:束半径|半径|beam radius)"
        match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    return _length_to_um(float(match.group(1)), match.group(2))


def _distance_um(text: str) -> float | None:
    unit_pattern = r"m|cm|mm|um|µm|米|厘米|毫米|微米"
    match = re.search(rf"距离\s*(\d+(?:\.\d+)?)\s*({unit_pattern})", text, re.IGNORECASE)
    if not match:
        match = re.search(rf"(\d+(?:\.\d+)?)\s*({unit_pattern})\s*处", text, re.IGNORECASE)
    if not match:
        return None
    return _length_to_um(float(match.group(1)), match.group(2))


def _length_to_um(value: float, unit: str) -> float:
    unit_lower = unit.lower()
    if unit_lower in {"m", "米"}:
        return value * 1_000_000.0
    if unit_lower in {"cm", "厘米"}:
        return value * 10_000.0
    if unit_lower in {"mm", "毫米"}:
        return value * 1000.0
    return value


def _target_from_parameters(parameters: dict[str, Any], current_target: Any) -> dict[str, Any]:
    target = dict(current_target) if isinstance(current_target, dict) else {}
    dimensions = parameters.get("geometry.robot_dimensions") or parameters.get("target.size")
    size_um = _box_size_um(str(dimensions or ""))
    if size_um:
        target["size_um"] = size_um
        target.setdefault("geometry_type", "box")
    material = parameters.get("materials.robot") or parameters.get("target.material")
    if material:
        target["material"] = _material_from_text(str(material))
    return target


def _box_size_um(text: str) -> list[float] | None:
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(cm|mm|um|µm|m|米|厘米|毫米|微米)\s*[x×]\s*"
        r"(\d+(?:\.\d+)?)\s*(cm|mm|um|µm|m|米|厘米|毫米|微米)?\s*[x×]\s*"
        r"(\d+(?:\.\d+)?)\s*(cm|mm|um|µm|m|米|厘米|毫米|微米)?",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    unit1 = match.group(2)
    unit2 = match.group(4) or unit1
    unit3 = match.group(6) or unit2
    return [
        _length_to_um(float(match.group(1)), unit1),
        _length_to_um(float(match.group(3)), unit2),
        _length_to_um(float(match.group(5)), unit3),
    ]


def _material_from_text(text: str) -> str:
    lowered = text.lower()
    if "g4_water" in lowered or "water" in lowered or "水" in text:
        return "G4_WATER"
    if "铁" in text or "fe" in lowered or "iron" in lowered:
        return "G4_Fe"
    if "铜" in text or "cu" in lowered or "copper" in lowered:
        return "G4_Cu"
    if "铝" in text or "al" in lowered or "aluminum" in lowered:
        return "G4_Al"
    return text.strip()
