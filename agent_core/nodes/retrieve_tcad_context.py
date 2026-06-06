"""Retrieve TCAD context - stub for MVP-1."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


async def retrieve_tcad_context(state: RadiationAgentState) -> dict:
    """Retrieve TCAD-related context. Stub for MVP-1."""
    return {"tcad_context": [], "current_node": "retrieve_tcad_context"}
