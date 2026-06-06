"""Retrieve Geant4 context from RAG."""

from __future__ import annotations

import json
from pathlib import Path

from agent_core.graph.state import RadiationAgentState
from agent_core.tools.g4rag_tool import G4RAGTool


async def retrieve_g4_context(state: RadiationAgentState) -> dict:
    """Retrieve Geant4-related context from g4rag knowledge base."""
    rag_route = state.get("rag_route", [])
    if "g4rag" not in rag_route:
        return {"g4_context": [], "current_node": "retrieve_g4_context"}

    task_spec = state.get("task_spec", {})
    user_query = state.get("user_query", "")
    job_id = state.get("job_id", "unknown")

    tool = G4RAGTool()
    context_pack = await tool.build_context_pack(user_query, task_spec)

    # Save context
    job_dir = Path("simulation_workspace/jobs") / job_id
    ctx_file = job_dir / "01_context" / "g4_context.json"
    ctx_file.write_text(json.dumps(context_pack, indent=2, ensure_ascii=False, default=str))

    g4_context = context_pack.get("retrieved_context", {}).get("manual_snippets", [])
    g4_context += context_pack.get("retrieved_context", {}).get("example_code", [])

    return {"g4_context": g4_context, "current_node": "retrieve_g4_context"}
