"""Retrieve TCAD context - stub for MVP-1."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


async def retrieve_tcad_context(state: RadiationAgentState) -> dict:
    """Retrieve TCAD-related context. Stub for MVP-1."""
    rag_route = state.get("rag_route", [])
    rag_required = state.get("rag_required_sources", [])
    rag_optional = state.get("rag_optional_sources", [])

    tcad_needed = (
        "tcadrag" in rag_route
        or "tcad" in rag_required
        or "tcad" in rag_optional
    )
    if not tcad_needed:
        return {"tcad_context": [], "current_node": "retrieve_tcad_context"}

    return {"tcad_context": [], "current_node": "retrieve_tcad_context"}
