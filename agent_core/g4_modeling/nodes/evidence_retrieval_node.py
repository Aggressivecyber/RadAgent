"""Evidence retrieval node — organizes RAG+Web evidence by modeling dimension.

Reads existing g4_context from state (populated by retrieve_required_context)
and organizes it into a dimension-keyed evidence pack.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, cast

from agent_core.config.workspace import get_stage_dir
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def evidence_retrieval_node(state: RadiationAgentState) -> dict[str, Any]:
    """Organize existing RAG/Web context into dimension-keyed evidence pack.

    Reads: g4_model_ir, g4_context, web_context, context_decision
    Writes: g4_model_ir.evidence (updated)
    Persists: 03_model_ir/evidence_context.json
    """
    model_ir_dict = state.get("g4_model_ir", {})
    g4_context: list[dict[str, Any]] = state.get("g4_context", [])  # type: ignore[assignment]
    web_context: list[dict[str, Any]] = state.get("web_context", [])  # type: ignore[assignment]
    raw_decision = state.get("context_decision", "block_no_context")
    job_id = state.get("job_id", "")

    from agent_core.g4_modeling.schemas.g4_model_ir import EvidencePack, G4ModelIR

    # Normalize context_decision to valid literal
    valid = ("allow_rag", "allow_with_web_supplement", "block_no_context")
    fallback: Literal["block_no_context"] = "block_no_context"
    context_decision = raw_decision if raw_decision in valid else fallback

    # Reconstruct model IR
    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Classify evidence by dimension
    geometry_evidence = []
    material_evidence = []
    source_evidence = []
    physics_evidence = []
    scoring_evidence = []

    for item in g4_context:
        text = item.get("text", "")
        source_type = item.get("source_type", item.get("doc_type", ""))

        # Classify by content keywords
        text_lower = text.lower() if text else ""
        geo_kw = ("geometry", "volume", "solid", "box", "cylinder", "placement")
        if any(kw in text_lower for kw in geo_kw):
            geometry_evidence.append(item)
        mat_kw = ("material", "nist", "density", "composition", "element")
        if any(kw in text_lower for kw in mat_kw):
            material_evidence.append(item)
        src_kw = ("source", "particle", "gun", "gps", "beam", "energy")
        if any(kw in text_lower for kw in src_kw):
            source_evidence.append(item)
        phys_kw = ("physics", "ftfp", "bert", "livermore", "emstandard")
        if any(kw in text_lower for kw in phys_kw):
            physics_evidence.append(item)
        sci_kw = ("scoring", "voxel", "dose", "edep", "mesh")
        if any(kw in text_lower for kw in sci_kw):
            scoring_evidence.append(item)

        # Also classify by source_type for better coverage
        if source_type == "example_code":
            # Code examples are useful for all dimensions
            geometry_evidence.append(item)
            source_evidence.append(item)

    # Add web context as supplementary
    for item in web_context:
        url = item.get("url", "")
        title = item.get("title", "")
        web_item = {
            **item,
            "source_type": "web_supplement",
            "source": url or title,
        }
        # Add to all dimensions as supplementary
        geometry_evidence.append(web_item)
        material_evidence.append(web_item)
        physics_evidence.append(web_item)

    evidence_pack = EvidencePack(
        evidence_decision=cast(
            Literal["allow_rag", "allow_with_web_supplement", "block_no_context"],
            context_decision,
        ),
        geometry=geometry_evidence,
        materials=material_evidence,
        source=source_evidence,
        physics=physics_evidence,
        scoring=scoring_evidence,
    )

    # Update model IR
    model_ir.evidence = evidence_pack
    model_ir.ledger.add_entry(
        node_name="evidence_retrieval_node",
        action="modify",
        target_id=model_ir.model_ir_id,
        description=(
            f"Organized evidence: geometry={len(geometry_evidence)}, "
            f"materials={len(material_evidence)}, source={len(source_evidence)}, "
            f"physics={len(physics_evidence)}, scoring={len(scoring_evidence)}"
        ),
        modified_fields=["evidence"],
    )

    # Persist
    if job_id:
        model_ir_dir = get_stage_dir(job_id, "03_model_ir")
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        ev_file = model_ir_dir / "evidence_context.json"
        ev_file.write_text(
            json.dumps(
                evidence_pack.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            )
        )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "evidence_pack": evidence_pack.model_dump(mode="json"),
        "current_node": "evidence_retrieval_node",
    }
