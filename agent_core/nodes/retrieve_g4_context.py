"""Retrieve Geant4 context from RAG."""

from __future__ import annotations

import json

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState
from agent_core.tools.g4rag_tool import G4RAGTool


async def retrieve_g4_context(state: RadiationAgentState) -> dict:
    """Retrieve Geant4-related context from g4rag knowledge base."""
    rag_route = state.get("rag_route", [])
    rag_required = state.get("rag_required_sources", [])
    rag_optional = state.get("rag_optional_sources", [])

    # Check both legacy route and new priority-based routing
    geant4_needed = (
        "g4rag" in rag_route
        or "geant4" in rag_required
        or "geant4" in rag_optional
    )
    if not geant4_needed:
        return {"g4_context": [], "current_node": "retrieve_g4_context"}

    # Check RAG registry for geant4 availability — skip MCP if unavailable
    rag_registry = state.get("rag_registry", {})
    g4_status = rag_registry.get("geant4", {})
    if not g4_status.get("available", False):
        return {"g4_context": [], "current_node": "retrieve_g4_context"}

    task_spec = state.get("task_spec", {})
    user_query = state.get("user_query", "")
    job_id = state.get("job_id", "unknown")

    tool = G4RAGTool()
    context_pack = await tool.build_context_pack(user_query, task_spec)

    # Save context
    job_dir = get_job_dir(job_id)
    ctx_file = job_dir / "01_context" / "g4_context.json"
    ctx_file.write_text(json.dumps(context_pack, indent=2, ensure_ascii=False, default=str))

    g4_context = context_pack.get("retrieved_context", {}).get("manual_snippets", [])
    g4_context += context_pack.get("retrieved_context", {}).get("example_code", [])

    return {"g4_context": g4_context, "current_node": "retrieve_g4_context"}
