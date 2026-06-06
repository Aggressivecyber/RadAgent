"""DEPRECATED: Retrieve Geant4 context from local knowledge_base.

This node is NOT wired into the main graph. The unified
retrieve_required_context node handles all RAG retrieval.
Kept for reference only.
"""

from __future__ import annotations

import json

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState
from agent_core.tools.geant4_rag_tool import Geant4RAGTool


async def retrieve_g4_context(state: RadiationAgentState) -> dict:
    """Retrieve Geant4-related context from knowledge_base/geant4/."""
    rag_required = state.get("rag_required_sources", [])
    rag_optional = state.get("rag_optional_sources", [])

    geant4_needed = "geant4" in rag_required or "geant4" in rag_optional
    if not geant4_needed:
        return {"g4_context": [], "current_node": "retrieve_g4_context"}

    # Check RAG registry for geant4 availability
    rag_registry = state.get("rag_registry", {})
    sources = rag_registry.get("sources", {})
    g4_info = sources.get("geant4", {})
    if not g4_info.get("available", False):
        return {"g4_context": [], "current_node": "retrieve_g4_context"}

    task_spec = state.get("task_spec", {})
    user_query = state.get("user_query", "")
    job_id = state.get("job_id", "unknown")

    tool = Geant4RAGTool()
    context_pack = await tool.build_context_pack(user_query, task_spec)

    # Save context
    job_dir = get_job_dir(job_id)
    ctx_file = job_dir / "01_context" / "g4_context.json"
    ctx_file.write_text(json.dumps(context_pack, indent=2, ensure_ascii=False, default=str))

    retrieved = context_pack.get("retrieved_context", {})
    g4_context = retrieved.get("manual_snippets", [])
    g4_context += retrieved.get("example_code", [])
    g4_context += retrieved.get("data_contracts", [])

    return {"g4_context": g4_context, "current_node": "retrieve_g4_context"}
