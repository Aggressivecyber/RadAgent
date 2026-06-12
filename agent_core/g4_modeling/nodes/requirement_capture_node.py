"""Requirement capture node — extracts structured requirements from user query.

This is the first node in the complex modeling pipeline. It uses LLM
to parse the user's natural language request into structured requirements
that drive all subsequent nodes.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from agent_core.g4_modeling.prompts.requirement_capture_prompt import (
    UNIFIED_MODELING_DRAFT_PROMPT,
)
from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState
from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_MODEL_IR

logger = logging.getLogger(__name__)


async def requirement_capture_node(state: RadiationAgentState) -> dict[str, Any]:
    """Extract a unified modeling draft from user query and task spec.

    Reads: user_query, task_spec, job_id
    Writes: g4_model_ir (initialized with core draft), evidence_pack (empty until retrieval)
    Persists: model IR stage requirements.json
    """
    user_query = state.get("user_query", "")
    task_spec = state.get("task_spec", {})
    job_id = state.get("job_id", "")

    if not job_id:
        return {"errors": ["requirement_capture: no job_id in state"]}

    # Initialize G4ModelIR skeleton
    from agent_core.g4_modeling.schemas.g4_model_ir import (
        ConstructionLedger,
        G4ModelIR,
        SimplificationPolicy,
    )

    model_ir = G4ModelIR(
        model_ir_id=f"mir_{job_id}",
        job_id=job_id,
        modeling_mode="realistic",
        target_system="",
        simplification_policy=SimplificationPolicy(),
        ledger=ConstructionLedger(),
    )

    # Record ledger entry
    model_ir.ledger.add_entry(
        node_name="requirement_capture_node",
        action="create",
        target_id=model_ir.model_ir_id,
        description="Initialized G4ModelIR skeleton",
        modified_fields=["model_ir_id", "job_id", "modeling_mode"],
    )

    draft: dict[str, Any] = {}
    try:
        from agent_core.models.gateway import get_model_gateway
        from agent_core.models.schemas import ModelTask, ModelTier

        gateway = get_model_gateway()
        prompt = UNIFIED_MODELING_DRAFT_PROMPT.format(
            user_query=user_query,
            task_spec=json.dumps(task_spec, indent=2, ensure_ascii=False),
        )
        result = await gateway.call(
            task=ModelTask.SIMPLE_EXTRACTION,
            tier=ModelTier.LITE,
            system_prompt="You are a Geant4 modeling drafter.",
            user_prompt=prompt,
            response_format="json",
            temperature=0.0,
            max_tokens=6144,
            metadata={
                "module_name": "g4_modeling_requirement_capture",
                "enable_thinking": False,
            },
        )

        if result.error:
            raise RuntimeError(result.error)

        draft = _draft_json_from_result(result)

    except Exception as exc:
        logger.warning("Unified modeling draft failed: %s", exc)

    requirements = _requirements_from_draft(draft, user_query, task_spec)
    model_ir.target_system = str(
        draft.get("target_system")
        or requirements.get("target_system")
        or user_query
    )
    model_ir.modeling_mode = str(draft.get("modeling_mode") or task_spec.get("modeling_mode") or "realistic")
    model_ir.open_issues = _string_list(draft.get("open_issues"))
    model_ir.components = _components_from_draft(draft, requirements, task_spec)
    model_ir.physics = _physics_from_draft(draft, task_spec)

    if not model_ir.components:
        from agent_core.g4_modeling.nodes.geometry_decomposition_node import (
            _fallback_components,
        )

        model_ir.components = _fallback_components(model_ir, requirements, task_spec)
    if model_ir.physics is None:
        from agent_core.g4_modeling.nodes.physics_list_node import (
            _default_physics_for_sources,
        )

        model_ir.physics = _default_physics_for_sources(
            _normalized_sources_for_physics(task_spec),
            [],
        )

    # Persist requirements
    model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
    model_ir_dir.mkdir(parents=True, exist_ok=True)
    req_file = model_ir_dir / "requirements.json"
    req_file.write_text(json.dumps(requirements, indent=2, ensure_ascii=False))

    # Record ledger
    model_ir.ledger.add_entry(
        node_name="requirement_capture_node",
        action="modify",
        target_id=model_ir.model_ir_id,
        description=(
            f"Captured draft: {len(model_ir.components)} components, "
            f"physics={getattr(model_ir.physics, 'physics_list', 'none')}"
        ),
        modified_fields=["target_system", "components", "physics", "open_issues"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "requirement_capture_node",
    }


def _heuristic_requirements(user_query: str, task_spec: dict) -> dict[str, Any]:
    """Fallback requirement extraction without LLM."""
    components: list[dict[str, str]] = []
    materials: list[dict[str, str]] = []
    sources: list[dict[str, str]] = []

    # Extract from task_spec if available
    particles = _source_particles(task_spec)
    target = task_spec.get("target", {})

    for index, particle in enumerate(particles):
        sources.append(_source_requirement(particle, index))

    if target:
        mat_name = target.get("material", "Si")
        materials.append(
            {
                "name": mat_name,
                "classification": "nist" if mat_name in ("Si", "Al", "Cu", "Ge") else "custom",
                "reason": "Target material from task specification",
            }
        )
        target.get("size_um", [1000, 1000, 300])
        components.append(
            {
                "component_id": "target_volume",
                "display_name": f"{mat_name} target",
                "component_type": "volume",
                "geometry_type": "box",
                "material": mat_name,
                "role": "Primary scoring region",
                "source": "user_specified",
            }
        )

    return {
        "target_system": user_query,
        "required_components": components,
        "required_materials": materials,
        "required_sources": sources,
        "required_outputs": task_spec.get("outputs", []),
        "forbidden_simplifications": [],
        "missing_information": [],
    }


def _draft_json_from_result(result: Any) -> dict[str, Any]:
    parsed = getattr(result, "parsed_json", None)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, str):
        try:
            data = json.loads(parsed)
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}
    content = str(getattr(result, "content", "") or "").strip()
    if not content:
        return {}
    try:
        data = json.loads(content)
    except Exception:
        try:
            data = json.loads(content[content.find("{") : content.rfind("}") + 1])
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


def _requirements_from_draft(
    draft: dict[str, Any],
    user_query: str,
    task_spec: dict[str, Any],
) -> dict[str, Any]:
    requirements = _heuristic_requirements(user_query, task_spec)
    if draft.get("target_system"):
        requirements["target_system"] = str(draft["target_system"])
    outputs = draft.get("required_outputs")
    if isinstance(outputs, list) and outputs:
        requirements["required_outputs"] = [str(item) for item in outputs if str(item).strip()]
    components = draft.get("components")
    if isinstance(components, list) and components:
        required_components: list[dict[str, Any]] = []
        for raw in components:
            requirement = _component_requirement_from_draft(raw)
            if requirement is not None:
                required_components.append(requirement)
        if required_components:
            requirements["required_components"] = required_components
            requirements["required_materials"] = _merge_material_requirements(
                requirements.get("required_materials", []),
                _material_requirements_from_components(required_components),
            )
    open_issues = _string_list(draft.get("open_issues"))
    missing = _string_list(draft.get("missing_information"))
    if open_issues or missing:
        requirements["missing_information"] = list(dict.fromkeys(
            [*requirements.get("missing_information", []), *missing, *open_issues]
        ))
    return requirements


def _component_requirement_from_draft(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    component_id = str(raw.get("component_id") or "").strip()
    if not component_id:
        return None
    display_name = str(raw.get("display_name") or component_id).strip()
    component_type = str(raw.get("component_type") or "volume").strip()
    geometry_type = str(raw.get("geometry_type") or "box").strip()
    material = str(raw.get("material_id") or raw.get("material") or "Air").strip()
    roles = raw.get("roles")
    role_text = ", ".join(str(role) for role in roles if str(role).strip()) if isinstance(roles, list) else ""
    source_evidence = raw.get("source_evidence")
    source = ""
    if isinstance(source_evidence, list) and source_evidence:
        source = str(source_evidence[0])
    if not source:
        source = "lite_draft"
    return {
        "component_id": component_id,
        "display_name": display_name,
        "component_type": component_type,
        "geometry_type": geometry_type,
        "material": material,
        "role": role_text or "modeling draft component",
        "source": source,
    }


def _material_requirements_from_components(
    components: list[dict[str, Any]],
) -> list[dict[str, str]]:
    materials: list[dict[str, str]] = []
    seen: set[str] = set()
    for component in components:
        material = str(component.get("material") or "").strip()
        if not material:
            continue
        key = _material_key(material)
        if not key or key in seen:
            continue
        seen.add(key)
        component_id = str(component.get("component_id") or "component").strip()
        materials.append(
            {
                "name": material,
                "classification": "nist" if _looks_like_nist_material(material) else "custom",
                "reason": f"Referenced by draft component '{component_id}'",
            }
        )
    return materials


def _merge_material_requirements(
    existing: Any,
    derived: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in [*(existing if isinstance(existing, list) else []), *derived]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("material") or "").strip()
        if not name:
            continue
        key = _material_key(name)
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "name": name,
                "classification": str(
                    raw.get("classification")
                    or ("nist" if _looks_like_nist_material(name) else "custom")
                ),
                "reason": str(raw.get("reason") or "Required by component material reference"),
            }
        )
    return merged


def _looks_like_nist_material(material: str) -> bool:
    if material.startswith("G4_"):
        return True
    return _material_key(material) in {
        "air",
        "al",
        "aluminum",
        "cu",
        "copper",
        "fe",
        "g4galactic",
        "ge",
        "galactic",
        "iron",
        "lead",
        "pb",
        "si",
        "silicon",
        "tungsten",
        "w",
        "water",
    }


def _material_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _components_from_draft(
    draft: dict[str, Any],
    requirements: dict[str, Any],
    task_spec: dict[str, Any],
) -> list[ComponentSpec]:
    raw_components = draft.get("components")
    if not isinstance(raw_components, list) or not raw_components:
        return []
    components: list[ComponentSpec] = []
    for raw in raw_components:
        try:
            component = ComponentSpec.model_validate(raw)
        except Exception as exc:
            logger.warning("Invalid draft component: %s", exc)
            continue
        components.append(component)
    if not components or not any(comp.component_type != "world" for comp in components):
        return []

    from agent_core.g4_modeling.nodes.geometry_decomposition_node import (
        _enrich_components_from_task_spec,
    )

    return _enrich_components_from_task_spec(components, requirements, task_spec)


def _physics_from_draft(draft: dict[str, Any], task_spec: dict[str, Any]) -> PhysicsSpec | None:
    raw_physics = draft.get("physics")
    if isinstance(raw_physics, dict) and raw_physics:
        try:
            return PhysicsSpec.model_validate(_normalize_physics_draft(raw_physics, task_spec))
        except Exception as exc:
            logger.warning("Invalid draft physics: %s", exc)

    from agent_core.g4_modeling.nodes.physics_list_node import (
        _default_physics_for_sources,
        _physics_from_user_options,
    )

    particle_type, energy, energy_unit = _physics_inputs(task_spec)
    physics = _physics_from_user_options(task_spec, particle_type, energy, energy_unit)
    if physics is not None:
        return physics
    return _default_physics_for_sources(_normalized_sources_for_physics(task_spec), [])


def _normalize_physics_draft(
    raw_physics: dict[str, Any],
    task_spec: dict[str, Any],
) -> dict[str, Any]:
    """Replace Lite-model prose evidence with stable non-placeholder references."""
    normalized = dict(raw_physics)
    raw_evidence = normalized.get("source_evidence")
    evidence = [str(item).strip() for item in raw_evidence if str(item).strip()] if isinstance(raw_evidence, list) else []
    cleaned = [
        item
        for item in evidence
        if not _is_placeholder_evidence(item)
    ]
    if not cleaned:
        physics_list = str(normalized.get("physics_list") or "physics_list").strip()
        cleaned = [f"task_spec.physics: requested physics_list={physics_list}"]
        options = task_spec.get("physics_options")
        if isinstance(options, dict) and options.get("physics_list"):
            cleaned = [
                f"task_spec.physics_options: physics_list={options['physics_list']}"
            ]
    normalized["source_evidence"] = cleaned
    return normalized


def _is_placeholder_evidence(value: str) -> bool:
    text = value.lower()
    return any(
        token in text
        for token in (
            "todo",
            "tbd",
            "fixme",
            "xxx",
            "placeholder",
            "unknown",
            "n/a",
            "default",
        )
    )


def _physics_inputs(task_spec: dict[str, Any]) -> tuple[str, float, str]:
    particles = _source_particles(task_spec)
    particle = particles[0] if particles else {}
    particle_type = str(particle.get("type", "proton"))
    energy = float(particle.get("energy_MeV", 10.0))
    energy_unit = str(particle.get("energy_unit", "MeV"))
    return particle_type, energy, energy_unit


def _normalized_sources_for_physics(task_spec: dict[str, Any]) -> list[Any]:
    sources: list[Any] = []
    for index, particle in enumerate(_source_particles(task_spec)):
        energy = SimpleNamespace(
            value=float(particle.get("energy_MeV", 10.0)),
            unit=str(particle.get("energy_unit", "MeV")),
            distribution=str(particle.get("energy_distribution", "mono")),
        )
        sources.append(
            SimpleNamespace(
                source_id=str(
                    particle.get("source_id")
                    or ("primary_source" if index == 0 else f"source_{index + 1}")
                ),
                particle_type=str(particle.get("type", "proton")),
                energy=energy,
            )
        )
    return sources


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _source_particles(task_spec: dict[str, Any]) -> list[dict[str, Any]]:
    composite = task_spec.get("particles")
    if isinstance(composite, list) and composite:
        return [item for item in composite if isinstance(item, dict)]
    particle = task_spec.get("particle")
    if isinstance(particle, dict) and particle:
        return [particle]
    return []


def _source_requirement(particle: dict[str, Any], index: int) -> dict[str, str]:
    energy_unit = str(particle.get("energy_unit", "MeV"))
    distribution = str(particle.get("energy_distribution", "mono"))
    direction = particle.get("direction")
    source_id = str(
        particle.get("source_id")
        or ("primary_source" if index == 0 else f"source_{index + 1}")
    )
    requirement = {
        "source_id": source_id,
        "particle_type": str(particle.get("type", "proton")),
        "energy": f"{particle.get('energy_MeV', 10)} {energy_unit}",
        "distribution": distribution,
        "geometry": _source_geometry(particle),
        "direction": json.dumps(direction) if direction is not None else "",
        "angular_distribution": str(particle.get("angular_distribution", "mono")),
    }
    spectrum_file = particle.get("spectrum_file")
    if spectrum_file:
        requirement["spectrum_file"] = str(spectrum_file)
    angular_file = particle.get("angular_spectrum_file")
    if angular_file:
        requirement["angular_spectrum_file"] = str(angular_file)
    return requirement


def _source_geometry(particle: dict[str, Any]) -> str:
    if particle.get("sigma_position_um") is not None:
        return "broad_beam"
    shape = particle.get("surface_shape")
    if shape and shape != "point":
        return "broad_beam"
    angular = particle.get("angular_distribution")
    if angular in {"isotropic", "cosine"}:
        return str(angular)
    return "pencil"
