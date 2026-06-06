"""Retrieve additional RAG context for error resolution during fix loop.

Used ONLY in the fix loop (classify_failure -> retrieve_error_context
-> write_fix_patch).  Results go into rag_error_context, NOT web_context.
"""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState
from agent_core.tools.geant4_rag_tool import Geant4RAGTool


async def retrieve_error_context(state: RadiationAgentState) -> dict:
    """Retrieve additional RAG context based on error information."""
    failure = state.get("failure_report", {})
    error_msg = failure.get("message", "")
    gate_name = failure.get("gate_name", "")

    tool = Geant4RAGTool()
    error_context = await tool.search(f"error: {gate_name} {error_msg}", top_k=3)

    return {
        "rag_error_context": error_context,
        "current_node": "retrieve_error_context",
    }
