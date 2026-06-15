"""Geometry decomposition node — decomposes target into component tree.

Uses LLM to break down the target system into individual components
with dimensions, materials, and placements.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_modeling.prompts.requirement_capture_prompt import (
    GEOMETRY_DECOMPOSITION_PROMPT,
)
from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.geometry_interface_spec import (
    GeometryInterfaceSpec,
)
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState
from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_MODEL_IR

logger = logging.getLogger(__name__)


async def geometry_decomposition_node(
    state: RadiationAgentState,
) -> dict[str, Any]:
    """Decompose the target system into a component tree.

    Reads: g4_model_ir (requirements, evidence, coordinate_system)
    Writes: g4_model_ir.components, g4_model_ir.interfaces
    Persists: model IR stage component_specs/*.json
    """
    model_ir_dict = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "")
    task_spec = state.get("task_spec", {})

    model_ir = G4ModelIR.model_validate(model_ir_dict)
    requirements = _load_requirements(job_id)

    existing_components = list(model_ir.components)
    if existing_components and any(
        comp.component_type != "world" for comp in existing_components
    ):
        components = _enrich_components_from_task_spec(
            existing_components,
            requirements,
            task_spec,
        )
        if not any(comp.component_type == "world" for comp in components):
            components.insert(
                0,
                ComponentSpec(
                    component_id="world",
                    display_name="World volume",
                    component_type="world",
                    geometry_type="box",
                    dimensions=_world_dimensions(_target_size_um(task_spec)),
                    material_id="Air",
                    source_evidence=["geometry_decomposition:inferred_world_volume"],
                ),
            )

        model_ir.components = components
        _resolve_sibling_box_overlaps(model_ir.components)
        _ensure_box_mothers_contain_children(model_ir.components)
        interfaces = _generate_interfaces(components)
        model_ir.interfaces = interfaces
        model_ir.ledger.add_entry(
            node_name="geometry_decomposition_node",
            action="create",
            target_id=model_ir.model_ir_id,
            description=(
                f"Normalized draft components, {len(components)} components, "
                f"{len(interfaces)} interfaces"
            ),
            modified_fields=["components", "interfaces"],
        )

        if job_id:
            model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
            specs_dir = model_ir_dir / "component_specs"
            specs_dir.mkdir(parents=True, exist_ok=True)
            for comp in components:
                spec_file = specs_dir / f"{comp.component_id}.json"
                spec_file.write_text(
                    json.dumps(comp.model_dump(mode="json"), indent=2, ensure_ascii=False)
                )

        component_tree = _build_tree(components)
        return {
            "g4_model_ir": model_ir.model_dump(mode="json"),
            "component_tree": component_tree,
            "current_node": "geometry_decomposition_node",
        }

    # Try LLM-based decomposition via model gateway
    components: list[ComponentSpec] = []
    try:
        from agent_core.models.gateway import get_model_gateway
        from agent_core.models.schemas import ModelTask, ModelTier

        gateway = get_model_gateway()

        # Prepare context
        evidence_text = _summarize_evidence(model_ir)
        coord_text = json.dumps(model_ir.coordinate_system.model_dump(), indent=2)

        req_text = json.dumps(requirements, indent=2, ensure_ascii=False)

        prompt = GEOMETRY_DECOMPOSITION_PROMPT.format(
            requirements=req_text,
            evidence=evidence_text,
            coordinate_system=coord_text,
        )
        result = await gateway.call(
            task=ModelTask.G4_MODELING,
            tier=ModelTier.PRO,
            system_prompt="You are a Geant4 geometry decomposition expert.",
            user_prompt=prompt,
            response_format="json",
            temperature=0.0,
            max_tokens=4096,
        )

        if result.error:
            raise RuntimeError(result.error)

        raw_content = result.content.strip()
        if "```" in raw_content:
            raw_content = raw_content.split("```")[1]
            if raw_content.startswith("json"):
                raw_content = raw_content[4:]

        raw_components = json.loads(raw_content.strip())
        if isinstance(raw_components, list):
            for raw in raw_components:
                try:
                    comp = ComponentSpec.model_validate(raw)
                    components.append(comp)
                except Exception as exc:
                    logger.warning("Invalid component spec: %s", exc)
                    model_ir.open_issues.append(f"Invalid component from LLM: {exc}")

    except Exception as exc:
        logger.warning("LLM geometry decomposition failed: %s", exc)
        components = _fallback_components(model_ir, requirements, task_spec)

    if not components:
        components = _fallback_components(model_ir, requirements, task_spec)

    components = _enrich_components_from_task_spec(components, requirements, task_spec)

    # The LLM occasionally returns only detector volumes and no world volume.
    # G4ModelIR requires at least one world component, so inject one if missing.
    if not any(comp.component_type == "world" for comp in components):
        components.insert(
            0,
            ComponentSpec(
                component_id="world",
                display_name="World volume",
                component_type="world",
                geometry_type="box",
                dimensions=_world_dimensions(_target_size_um(task_spec)),
                material_id="Air",
                source_evidence=["geometry_decomposition:inferred_world_volume"],
            ),
        )

    # Update model IR
    model_ir.components = components
    _resolve_sibling_box_overlaps(model_ir.components)
    _ensure_box_mothers_contain_children(model_ir.components)

    # Generate interfaces from parent-child relationships
    interfaces = _generate_interfaces(components)
    model_ir.interfaces = interfaces

    # Record ledger
    model_ir.ledger.add_entry(
        node_name="geometry_decomposition_node",
        action="create",
        target_id=model_ir.model_ir_id,
        description=f"Created {len(components)} components, {len(interfaces)} interfaces",
        modified_fields=["components", "interfaces"],
    )

    # Persist component specs
    if job_id:
        model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
        specs_dir = model_ir_dir / "component_specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        for comp in components:
            spec_file = specs_dir / f"{comp.component_id}.json"
            spec_file.write_text(
                json.dumps(comp.model_dump(mode="json"), indent=2, ensure_ascii=False)
            )

    # Update component_tree for state
    component_tree = _build_tree(components)

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "component_tree": component_tree,
        "current_node": "geometry_decomposition_node",
    }


def _summarize_evidence(model_ir: G4ModelIR) -> str:
    """Create a concise text summary of evidence for LLM context."""
    if model_ir.evidence is None:
        return "No evidence available."
    parts: list[str] = []
    for dim in ("geometry", "materials", "source", "physics", "scoring"):
        items = getattr(model_ir.evidence, dim, [])
        if items:
            texts = [str(i.get("text", i.get("code", "")))[:200] for i in items[:3]]
            parts.append(f"{dim}: " + "; ".join(texts))
    return "\n".join(parts) if parts else "No detailed evidence available."


def _generate_interfaces(
    components: list[ComponentSpec],
) -> list[GeometryInterfaceSpec]:
    """Generate geometry interfaces from parent-child relationships."""
    interfaces: list[GeometryInterfaceSpec] = []
    for comp in components:
        if comp.mother_volume is not None:
            iface = GeometryInterfaceSpec(
                interface_id=f"iface_{comp.component_id}_{comp.mother_volume}",
                component_a=comp.mother_volume,
                component_b=comp.component_id,
                relationship="contains",
                expected_gap_um=0.0,
                overlap_allowed=False,
                overlap_check_enabled=True,
            )
            interfaces.append(iface)
    return interfaces


def _build_tree(components: list[ComponentSpec]) -> dict[str, Any]:
    """Build a component tree dict from flat list."""
    tree: dict[str, list[str]] = {}
    for comp in components:
        mother = comp.mother_volume or "root"
        tree.setdefault(mother, []).append(comp.component_id)
    return tree


def _load_requirements(job_id: str) -> dict[str, Any]:
    if not job_id:
        return {}
    req_file = get_stage_dir(job_id, STAGE_MODEL_IR) / "requirements.json"
    if not req_file.is_file():
        return {}
    try:
        data = json.loads(req_file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _fallback_components(
    model_ir: G4ModelIR,
    requirements: dict[str, Any] | None = None,
    task_spec: dict[str, Any] | None = None,
) -> list[ComponentSpec]:
    """Create minimal fallback components without LLM."""
    requirements = requirements or {}
    task_spec = task_spec or {}
    required_components = requirements.get("required_components")
    if not isinstance(required_components, list) or not required_components:
        return [
            ComponentSpec(
                component_id="world",
                display_name="World volume",
                component_type="world",
                geometry_type="box",
                dimensions={"dx": 5000, "dy": 5000, "dz": 5000},
                material_id="air",
                source_evidence=["fallback: no LLM decomposition available"],
                open_issues=["LLM decomposition failed; only a world volume was available"],
            ),
        ]

    outputs = _requested_outputs(requirements, task_spec)
    target_size = _target_size_um(task_spec)
    target_material = _target_material(task_spec)
    world_id = _world_component_id(required_components) or "world"
    components: list[ComponentSpec] = []

    for raw in required_components:
        if not isinstance(raw, dict):
            continue
        component_type = str(raw.get("component_type") or "volume")
        is_world = component_type == "world"
        component_id = str(raw.get("component_id") or ("world" if is_world else "component"))
        material_raw = raw.get("material")
        material_missing = not is_world and not material_raw and not target_material
        material = str(
            material_raw
            or ("Air" if is_world else target_material or "material_pending_user_selection")
        )
        role_text = str(raw.get("role") or "")
        dimensions = _component_dimensions(
            raw,
            is_world=is_world,
            target_size=target_size,
            material=material,
            target_material=target_material,
        )
        roles, sensitive = _roles_from_requirement(role_text, outputs)
        source_kind = raw.get("source") or "user_specified"
        source_evidence = [
            f"requirements.json:{component_id}:{source_kind}",
        ]
        open_issues: list[str] = []
        requires_confirmation = False
        if material_missing:
            open_issues.append(
                f"No material was specified for component '{component_id}'"
            )
            requires_confirmation = True
        if (
            not is_world
            and target_size
            and material.lower() == (target_material or "").lower()
            and task_spec.get("metadata", {}).get("target_lateral_extent_assumption")
        ):
            open_issues.append(str(task_spec["metadata"]["target_lateral_extent_assumption"]))
            requires_confirmation = True
        if not dimensions:
            open_issues.append(
                f"No numeric dimensions were available for component '{component_id}'"
            )
            requires_confirmation = True

        components.append(
            ComponentSpec(
                component_id=component_id,
                display_name=str(raw.get("display_name") or component_id),
                component_type=component_type,  # type: ignore[arg-type]
                geometry_type=str(raw.get("geometry_type") or "box"),  # type: ignore[arg-type]
                dimensions=dimensions,
                material_id=material,
                placement={"position": [0.0, 0.0, 0.0], "rotation": [0.0, 0.0, 0.0]},
                mother_volume=None if is_world else world_id,
                sensitive=sensitive,
                roles=roles,
                source_evidence=source_evidence,
                open_issues=open_issues,
                requires_confirmation=requires_confirmation,
            )
        )

    if not any(comp.component_type == "world" for comp in components):
        components.insert(
            0,
            ComponentSpec(
                component_id=world_id,
                display_name="World volume",
                component_type="world",
                geometry_type="box",
                dimensions=_world_dimensions(target_size),
                material_id="Air",
                source_evidence=["requirements.json:inferred_world_from_target"],
            ),
        )
    return components


def _enrich_components_from_task_spec(
    components: list[ComponentSpec],
    requirements: dict[str, Any],
    task_spec: dict[str, Any],
) -> list[ComponentSpec]:
    target_size = _target_size_um(task_spec)
    if not target_size:
        return components

    target_dimensions = {
        "dx": target_size[0],
        "dy": target_size[1],
        "dz": target_size[2],
    }
    target_material = _target_material(task_spec)
    target_geometry = _target_geometry_type(task_spec)
    target_components = _select_task_target_components(
        components,
        target_material=target_material,
        target_geometry=target_geometry,
    )

    for comp in components:
        if comp.component_type == "world":
            _fill_missing_box_dimensions(
                comp,
                defaults=_world_dimensions(target_size),
                evidence="task_spec.target.size_um: inferred world envelope around target",
            )
            continue
        if comp in target_components:
            filled = _fill_missing_box_dimensions(
                comp,
                defaults=target_dimensions,
                evidence="task_spec.target.size_um: structured target dimensions",
            )
            assumption = task_spec.get("metadata", {}).get("target_lateral_extent_assumption")
            if assumption and any(axis in filled for axis in ("dx", "dy")):
                if str(assumption) not in comp.open_issues:
                    comp.open_issues.append(str(assumption))
                comp.requires_confirmation = True

    return components


def _select_task_target_components(
    components: list[ComponentSpec],
    *,
    target_material: str | None,
    target_geometry: str | None,
) -> list[ComponentSpec]:
    candidates = [
        comp
        for comp in components
        if comp.component_type != "world"
        and (not target_geometry or comp.geometry_type == target_geometry)
        and (not target_material or _material_names_match(comp.material_id, target_material))
    ]
    if candidates:
        return candidates

    non_world_boxes = [
        comp
        for comp in components
        if comp.component_type != "world"
        and (not target_geometry or comp.geometry_type == target_geometry)
    ]
    if len(non_world_boxes) == 1:
        return non_world_boxes
    return []


def _fill_missing_box_dimensions(
    comp: ComponentSpec,
    *,
    defaults: dict[str, float],
    evidence: str,
) -> list[str]:
    if comp.geometry_type != "box":
        return []
    dimensions = dict(comp.dimensions)
    filled: list[str] = []
    for axis in ("dx", "dy", "dz"):
        if not _is_number(dimensions.get(axis)) and _is_number(defaults.get(axis)):
            dimensions[axis] = float(defaults[axis])
            filled.append(axis)
    if filled:
        comp.dimensions = dimensions
        evidence_entry = f"{evidence}; filled missing {', '.join(filled)}"
        if evidence_entry not in comp.source_evidence:
            comp.source_evidence.append(evidence_entry)
    return filled


def _target_geometry_type(task_spec: dict[str, Any]) -> str | None:
    target = task_spec.get("target")
    if not isinstance(target, dict):
        return None
    geometry = target.get("geometry_type")
    return str(geometry) if geometry else None


def _material_names_match(left: str, right: str) -> bool:
    lhs = _normalize_material_name(left)
    rhs = _normalize_material_name(right)
    if lhs == rhs:
        return True
    aliases = {
        "silicon": {"silicon", "si", "g4si"},
        "air": {"air", "g4air"},
    }
    for names in aliases.values():
        if lhs in names and rhs in names:
            return True
    return lhs in rhs or rhs in lhs


def _resolve_sibling_box_overlaps(components: list[ComponentSpec]) -> None:
    siblings: dict[str | None, list[ComponentSpec]] = {}
    for comp in components:
        siblings.setdefault(comp.mother_volume, []).append(comp)

    for children in siblings.values():
        if len(children) < 2:
            continue
        for child in children:
            if not _looks_like_downstream_detector(child):
                continue
            moved = _move_after_overlapping_siblings(child, children)
            if moved and "geometry_decomposition:placed downstream of shielding stack to avoid overlap" not in child.source_evidence:
                child.source_evidence.append(
                    "geometry_decomposition:placed downstream of shielding stack to avoid overlap"
                )


def _ensure_box_mothers_contain_children(
    components: list[ComponentSpec],
    *,
    clearance_um: float = 1000.0,
) -> None:
    by_id = {comp.component_id: comp for comp in components}
    children_by_mother: dict[str, list[ComponentSpec]] = {}
    for comp in components:
        if comp.mother_volume:
            children_by_mother.setdefault(comp.mother_volume, []).append(comp)

    changed = True
    iterations = 0
    while changed and iterations < len(components):
        changed = False
        iterations += 1
        for mother_id, children in children_by_mother.items():
            mother = by_id.get(mother_id)
            if mother is None or mother.geometry_type != "box":
                continue
            box_children = [child for child in children if child.geometry_type == "box"]
            if not box_children:
                continue
            if _expand_box_mother_for_children(
                mother,
                box_children,
                clearance_um=clearance_um,
            ):
                changed = True


def _expand_box_mother_for_children(
    mother: ComponentSpec,
    children: list[ComponentSpec],
    *,
    clearance_um: float,
) -> bool:
    dimensions = dict(mother.dimensions)
    expanded_axes: list[str] = []
    for axis_index, axis in enumerate(("x", "y", "z")):
        current_half = _dimension_half(dimensions, axis)
        required_half = max(
            abs(child_pos + sign * child_half)
            for child in children
            for child_pos, child_half in [
                (_component_position(child)[axis_index], _component_half_lengths(child)[axis_index])
            ]
            for sign in (-1.0, 1.0)
        )
        if required_half <= 0:
            continue
        if required_half > current_half:
            target_full = 2.0 * (required_half + clearance_um)
            dimensions[f"d{axis}"] = target_full
            dimensions.pop(f"half_{axis}", None)
            expanded_axes.append(axis)

    if not expanded_axes:
        return False

    mother.dimensions = dimensions
    evidence = (
        "geometry_decomposition:expanded mother volume to contain daughter "
        f"placements on {', '.join(expanded_axes)}"
    )
    if evidence not in mother.source_evidence:
        mother.source_evidence.append(evidence)
    return True


def _looks_like_downstream_detector(comp: ComponentSpec) -> bool:
    text = " ".join(
        [
            comp.component_id,
            comp.display_name,
            comp.component_type,
            " ".join(comp.roles),
            " ".join(comp.source_evidence),
        ]
    ).lower()
    return "detector" in text or "downstream" in text or comp.sensitive


def _move_after_overlapping_siblings(
    target: ComponentSpec,
    siblings: list[ComponentSpec],
    *,
    clearance_um: float = 500.0,
) -> bool:
    if target.geometry_type != "box":
        return False
    target_pos = _component_position(target)
    target_hz = _component_half_z(target)
    if target_hz <= 0:
        return False

    moved = False
    for sibling in siblings:
        if sibling is target or sibling.geometry_type != "box":
            continue
        if not _box_components_overlap(target, sibling):
            continue
        sibling_pos = _component_position(sibling)
        sibling_hz = _component_half_z(sibling)
        candidate_z = sibling_pos[2] + sibling_hz + target_hz + clearance_um
        if candidate_z > target_pos[2]:
            target_pos[2] = candidate_z
            moved = True

    if moved:
        placement = target.placement
        placement.position = target_pos
        target.placement = placement
    return moved


def _box_components_overlap(left: ComponentSpec, right: ComponentSpec) -> bool:
    left_pos = _component_position(left)
    right_pos = _component_position(right)
    left_half = _component_half_lengths(left)
    right_half = _component_half_lengths(right)
    return all(
        abs(lp - rp) < (lh + rh)
        for lp, rp, lh, rh in zip(left_pos, right_pos, left_half, right_half)
    )


def _component_position(comp: ComponentSpec) -> list[float]:
    return [float(value) for value in comp.placement.position]


def _component_half_lengths(comp: ComponentSpec) -> list[float]:
    dims = comp.dimensions
    return [
        _dimension_half(dims, "x"),
        _dimension_half(dims, "y"),
        _dimension_half(dims, "z"),
    ]


def _component_half_z(comp: ComponentSpec) -> float:
    return _component_half_lengths(comp)[2]


def _dimension_half(dimensions: dict[str, float], axis: str) -> float:
    half_key = f"half_{axis}"
    full_key = f"d{axis}"
    if _is_number(dimensions.get(half_key)):
        return float(dimensions[half_key])
    if _is_number(dimensions.get(full_key)):
        return float(dimensions[full_key]) / 2.0
    return 0.0


def _normalize_material_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _world_component_id(required_components: list[Any]) -> str | None:
    for raw in required_components:
        if isinstance(raw, dict) and raw.get("component_type") == "world":
            cid = raw.get("component_id")
            return str(cid) if cid else None
    return None


def _requested_outputs(
    requirements: dict[str, Any],
    task_spec: dict[str, Any],
) -> set[str]:
    outputs: set[str] = set()
    for source in (requirements.get("required_outputs"), task_spec.get("outputs")):
        if isinstance(source, list):
            outputs.update(str(item) for item in source)
    return outputs


def _target_size_um(task_spec: dict[str, Any]) -> list[float] | None:
    target = task_spec.get("target")
    if not isinstance(target, dict):
        return None
    raw = target.get("size_um")
    if not isinstance(raw, list) or len(raw) != 3:
        return None
    try:
        return [float(raw[0]), float(raw[1]), float(raw[2])]
    except (TypeError, ValueError):
        return None


def _target_material(task_spec: dict[str, Any]) -> str | None:
    target = task_spec.get("target")
    if not isinstance(target, dict):
        return None
    material = target.get("material")
    return str(material) if material else None


def _component_dimensions(
    raw: dict[str, Any],
    *,
    is_world: bool,
    target_size: list[float] | None,
    material: str,
    target_material: str | None,
) -> dict[str, float]:
    explicit = raw.get("dimensions")
    if isinstance(explicit, dict):
        return {
            str(key): float(value)
            for key, value in explicit.items()
            if _is_number(value)
        }
    raw_size = raw.get("size_um")
    if isinstance(raw_size, list) and len(raw_size) == 3 and all(_is_number(v) for v in raw_size):
        return {"dx": float(raw_size[0]), "dy": float(raw_size[1]), "dz": float(raw_size[2])}
    if is_world:
        return _world_dimensions(target_size)
    if target_size and material.lower() == (target_material or "").lower():
        return {"dx": target_size[0], "dy": target_size[1], "dz": target_size[2]}
    thickness = raw.get("thickness_um")
    if _is_number(thickness):
        dz = float(thickness)
        lateral = max(10.0 * dz, 10000.0)
        return {"dx": lateral, "dy": lateral, "dz": dz}
    return {}


def _world_dimensions(target_size: list[float] | None) -> dict[str, float]:
    if not target_size:
        return {"dx": 5000.0, "dy": 5000.0, "dz": 5000.0}
    envelope = max(max(target_size) * 5.0, max(target_size) + 2000.0)
    return {"dx": envelope, "dy": envelope, "dz": envelope}


def _roles_from_requirement(role_text: str, outputs: set[str]) -> tuple[list[str], bool]:
    role_lower = role_text.lower()
    output_lower = {item.lower() for item in outputs}
    sensitive = any(
        token in role_lower
        for token in ("sensitive", "detector", "score", "scoring", "energy deposition", "dose")
    )
    roles: list[str] = []
    if sensitive or any(item in output_lower for item in ("edep", "energy_deposition", "event_table")):
        roles.append("edep_region")
    if "dose" in role_lower or any("dose" in item for item in output_lower):
        roles.append("dose_scoring_region")
    if any(item in output_lower for item in ("dose_3d", "dose_map", "dose_distribution")):
        roles.append("3d_dose_map")
    if any(item in output_lower for item in ("edep_3d", "energy_deposition_map")):
        roles.append("3d_edep_map")
    return list(dict.fromkeys(roles)), sensitive or bool(roles)


def _is_number(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True
