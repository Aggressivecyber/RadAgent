"""Retrieve SPICE context - stub for MVP-1."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


async def retrieve_spice_context(state: RadiationAgentState) -> dict:
    """Retrieve SPICE-related context. Stub for MVP-1."""
    rag_route = state.get("rag_route", [])
    rag_required = state.get("rag_required_sources", [])
    rag_optional = state.get("rag_optional_sources", [])

    spice_needed = (
        "spicerag" in rag_route
        or "spice" in rag_required
        or "spice" in rag_optional
    )
    if not spice_needed:
        return {"spice_context": [], "current_node": "retrieve_spice_context"}

    return {"spice_context": [], "current_node": "retrieve_spice_context"}
