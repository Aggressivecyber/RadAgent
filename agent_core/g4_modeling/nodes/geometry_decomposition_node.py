"""Geometry decomposition node — decomposes target into component tree.

Uses LLM to break down the target system into individual components
with dimensions, materials, and placements.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.config.workspace import get_stage_dir
from agent_core.g4_modeling.prompts.requirement_capture_prompt import (
    GEOMETRY_DECOMPOSITION_PROMPT,
)
from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.geometry_interface_spec import (
    GeometryInterfaceSpec,
)
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def geometry_decomposition_node(
    state: RadiationAgentState,
) -> dict[str, Any]:
    """Decompose the target system into a component tree.

    Reads: g4_model_ir (requirements, evidence, coordinate_system)
    Writes: g4_model_ir.components, g4_model_ir.interfaces
    Persists: 03_model_ir/component_specs/*.json
    """
    model_ir_dict = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "")

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Try LLM-based decomposition via model gateway
    components: list[ComponentSpec] = []
    try:
        from agent_core.models.gateway import get_model_gateway
        from agent_core.models.schemas import ModelTask, ModelTier

        gateway = get_model_gateway()

        # Prepare context
        evidence_text = _summarize_evidence(model_ir)
        coord_text = json.dumps(model_ir.coordinate_system.model_dump(), indent=2)

        # Load requirements from file if available
        req_text = "{}"
        if job_id:
            req_file = get_stage_dir(job_id, "03_model_ir") / "requirements.json"
            if req_file.is_file():
                req_text = req_file.read_text()

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
                    model_ir.open_issues.append(
                        f"Invalid component from LLM: {exc}"
                    )

    except Exception as exc:
        logger.warning("LLM geometry decomposition failed: %s", exc)
        components = _fallback_components(model_ir)

    # Update model IR
    model_ir.components = components

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
        model_ir_dir = get_stage_dir(job_id, "03_model_ir")
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


def _fallback_components(model_ir: G4ModelIR) -> list[ComponentSpec]:
    """Create minimal fallback components without LLM."""
    return [
        ComponentSpec(
            component_id="world",
            display_name="World volume",
            component_type="world",
            geometry_type="box",
            dimensions={"dx": 5000, "dy": 5000, "dz": 5000},
            material_id="air",
            source_evidence=["fallback: no LLM decomposition available"],
            open_issues=["LLM decomposition failed — using minimal fallback"],
        ),
    ]
