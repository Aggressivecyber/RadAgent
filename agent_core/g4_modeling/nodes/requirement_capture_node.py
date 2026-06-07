"""Requirement capture node — extracts structured requirements from user query.

This is the first node in the complex modeling pipeline. It uses LLM
to parse the user's natural language request into structured requirements
that drive all subsequent nodes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.config.workspace import get_stage_dir
from agent_core.g4_modeling.prompts.requirement_capture_prompt import (
    REQUIREMENT_CAPTURE_PROMPT,
)
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def requirement_capture_node(state: RadiationAgentState) -> dict[str, Any]:
    """Extract structured requirements from user query and task spec.

    Reads: user_query, task_spec, job_id
    Writes: g4_model_ir (initialized), evidence_pack (stub)
    Persists: 03_model_ir/requirements.json
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

    # Try LLM-based requirement extraction
    requirements: dict[str, Any] = {}
    try:
        from agent_core.llm import get_llm

        llm = get_llm(temperature=0)
        prompt = REQUIREMENT_CAPTURE_PROMPT.format(
            user_query=user_query,
            task_spec=json.dumps(task_spec, indent=2, ensure_ascii=False),
        )
        response = await llm.ainvoke(prompt)
        raw_content = response.content
        # Handle list content (multimodal responses)
        if isinstance(raw_content, list):
            raw_content = " ".join(
                str(p) if isinstance(p, str) else "" for p in raw_content
            )
        content_str: str = raw_content

        # Strip markdown code fences if present
        if "```" in content_str:
            content_str = content_str.split("```")[1]
            if content_str.startswith("json"):
                content_str = content_str[4:]

        requirements = json.loads(content_str.strip())
        model_ir.target_system = requirements.get("target_system", "")

    except Exception as exc:
        logger.warning("LLM requirement capture failed: %s", exc)
        # Fallback: extract from task_spec
        requirements = _heuristic_requirements(user_query, task_spec)
        model_ir.target_system = requirements.get("target_system", user_query)

    # Persist requirements
    model_ir_dir = get_stage_dir(job_id, "03_model_ir")
    model_ir_dir.mkdir(parents=True, exist_ok=True)
    req_file = model_ir_dir / "requirements.json"
    req_file.write_text(json.dumps(requirements, indent=2, ensure_ascii=False))

    # Record ledger
    model_ir.ledger.add_entry(
        node_name="requirement_capture_node",
        action="modify",
        target_id=model_ir.model_ir_id,
        description=f"Captured requirements: "
        f"{len(requirements.get('required_components', []))} components, "
        f"{len(requirements.get('required_materials', []))} materials",
        modified_fields=["target_system"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "requirement_capture_node",
    }


def _heuristic_requirements(
    user_query: str, task_spec: dict
) -> dict[str, Any]:
    """Fallback requirement extraction without LLM."""
    components: list[dict[str, str]] = []
    materials: list[dict[str, str]] = []
    sources: list[dict[str, str]] = []

    # Extract from task_spec if available
    particle = task_spec.get("particle", {})
    target = task_spec.get("target", {})

    if particle:
        sources.append({
            "particle_type": particle.get("type", "proton"),
            "energy": f"{particle.get('energy_MeV', 10)} MeV",
            "distribution": "mono",
            "geometry": "pencil",
        })

    if target:
        mat_name = target.get("material", "Si")
        materials.append({
            "name": mat_name,
            "classification": "nist" if mat_name in ("Si", "Al", "Cu", "Ge") else "custom",
            "reason": "Target material from task specification",
        })
        target.get("size_um", [1000, 1000, 300])
        components.append({
            "component_id": "target_volume",
            "display_name": f"{mat_name} target",
            "component_type": "volume",
            "geometry_type": "box",
            "material": mat_name,
            "role": "Primary scoring region",
            "source": "user_specified",
        })

    return {
        "target_system": user_query,
        "required_components": components,
        "required_materials": materials,
        "required_sources": sources,
        "required_outputs": task_spec.get("outputs", []),
        "forbidden_simplifications": [],
        "missing_information": [],
    }
