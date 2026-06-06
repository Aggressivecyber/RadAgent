"""Retrieve SPICE context - stub for MVP-1."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


async def retrieve_spice_context(state: RadiationAgentState) -> dict:
    """Retrieve SPICE-related context. Stub for MVP-1."""
    return {"spice_context": [], "current_node": "retrieve_spice_context"}
