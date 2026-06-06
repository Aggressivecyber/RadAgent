"""DEPRECATED: Retrieve SPICE context — stub for MVP-1.

This node is NOT wired into the main graph. The unified
retrieve_required_context node handles all RAG retrieval.
Kept for reference only.
"""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


async def retrieve_spice_context(state: RadiationAgentState) -> dict:
    """Retrieve SPICE-related context. Stub for MVP-1."""
    rag_required = state.get("rag_required_sources", [])
    rag_optional = state.get("rag_optional_sources", [])

    spice_needed = "spice" in rag_required or "spice" in rag_optional
    if not spice_needed:
        return {"spice_context": [], "current_node": "retrieve_spice_context"}

    return {"spice_context": [], "current_node": "retrieve_spice_context"}
