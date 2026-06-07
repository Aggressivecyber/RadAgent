"""Physics list node — selects physics list with reasoning.

LLM-driven node: selects appropriate physics list based on
particle type, energy range, and scoring requirements.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_modeling.prompts.requirement_capture_prompt import (
    PHYSICS_SELECTION_PROMPT,
)
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def physics_list_node(state: RadiationAgentState) -> dict[str, Any]:
    """Select physics list with reasoning.

    Reads: g4_model_ir (sources, components, materials, evidence)
    Writes: g4_model_ir.physics
    """
    model_ir_dict = state.get("g4_model_ir", {})
    state.get("job_id", "")

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Gather context
    particle_type = "proton"
    energy = 10.0
    energy_unit = "MeV"
    if model_ir.sources:
        src = model_ir.sources[0]
        particle_type = src.particle_type
        energy = src.energy.value
        energy_unit = src.energy.unit

    material_names = [m.name for m in model_ir.materials]
    scoring_reqs = [s.scoring_type for s in model_ir.scoring]

    # Try LLM-based selection
    physics: PhysicsSpec | None = None
    try:
        from agent_core.llm import get_llm

        llm = get_llm(temperature=0)

        evidence_text = ""
        if model_ir.evidence and model_ir.evidence.physics:
            evidence_text = json.dumps(
                model_ir.evidence.physics[:3], indent=2, ensure_ascii=False
            )

        prompt = PHYSICS_SELECTION_PROMPT.format(
            particle_type=particle_type,
            energy=energy,
            energy_unit=energy_unit,
            materials=", ".join(material_names) if material_names else "unknown",
            scoring_requirements=", ".join(scoring_reqs) if scoring_reqs else "edep, dose",
            evidence=evidence_text or "No specific physics evidence available",
        )
        response = await llm.ainvoke(prompt)
        raw_content = response.content
        if isinstance(raw_content, list):
            raw_content = " ".join(
                str(p) if isinstance(p, str) else "" for p in raw_content
            )
        content_str: str = raw_content

        if "```" in content_str:
            content_str = content_str.split("```")[1]
            if content_str.startswith("json"):
                content_str = content_str[4:]

        raw = json.loads(content_str.strip())
        physics = PhysicsSpec.model_validate(raw)

    except Exception as exc:
        logger.warning("LLM physics selection failed: %s", exc)
        physics = _default_physics(particle_type, energy, energy_unit)

    model_ir.physics = physics

    model_ir.ledger.add_entry(
        node_name="physics_list_node",
        action="create",
        target_id="physics",
        description=f"Selected physics list: {physics.physics_list}",
        modified_fields=["physics"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "physics_list_node",
    }


def _default_physics(
    particle_type: str, energy: float, energy_unit: str
) -> PhysicsSpec:
    """Provide a reasonable default physics selection."""
    if particle_type.lower() in ("gamma", "e-", "e+", "electron", "positron"):
        if energy < 1.0 and energy_unit == "GeV":
            pl = "Livermore"
            reason = (
                f"Low-energy electromagnetic particle ({particle_type} at "
                f"{energy} {energy_unit}) — Livermore provides accurate "
                f"low-energy EM processes for dosimetry applications"
            )
        else:
            pl = "FTFP_BERT"
            reason = (
                f"Electromagnetic particle ({particle_type} at {energy} "
                f"{energy_unit}) — FTFP_BERT provides comprehensive EM "
                f"and hadronic coverage"
            )
    elif particle_type.lower() in ("neutron",):
        pl = "QGSP_BIC_HP"
        reason = (
            f"Neutron transport at {energy} {energy_unit} — "
            f"QGSP_BIC_HP with NeutronHP provides accurate thermal and "
            f"epithermal neutron transport"
        )
    else:
        pl = "QGSP_BIC"
        reason = (
            f"Proton/hadron at {energy} {energy_unit} — "
            f"QGSP_BIC provides accurate hadronic cascade modeling "
            f"for proton therapy energy ranges"
        )

    return PhysicsSpec(
        physics_list=pl,
        selection_reasoning=reason,
        source_evidence=[f"Default selection for {particle_type} at {energy} {energy_unit}"],
    )
