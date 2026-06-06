"""Retrieve additional context for error resolution."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState
from agent_core.tools.g4rag_tool import G4RAGTool


async def retrieve_error_context(state: RadiationAgentState) -> dict:
    """Retrieve additional RAG context based on error information."""
    failure = state.get("failure_report", {})
    error_msg = failure.get("message", "")
    gate_name = failure.get("gate_name", "")

    tool = G4RAGTool()
    error_context = await tool.search(f"error: {gate_name} {error_msg}", top_k=3)

    return {
        "web_context": error_context,
        "current_node": "retrieve_error_context",
    }
