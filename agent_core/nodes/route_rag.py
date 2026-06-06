"""RAG routing node — outputs only logical names (geant4, tcad, spice)."""

from __future__ import annotations

import json

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState
from agent_core.tools.rag_router import RAGRouter


async def route_rag(state: RadiationAgentState) -> dict:
    """Determine which RAG sources to query based on task spec."""
    task_spec = state.get("task_spec", {})
    job_id = state.get("job_id", "unknown")

    router = RAGRouter()
    priority = router.route(task_spec)

    # Save routing decision
    job_dir = get_job_dir(job_id)
    route_file = job_dir / "01_context" / "rag_route.json"
    route_file.write_text(
        json.dumps(
            {
                "task_scope": task_spec.get("simulation_scope", []),
                "required_sources": priority["required"],
                "optional_sources": priority["optional"],
            },
            indent=2,
        )
    )

    return {
        "rag_required_sources": priority["required"],
        "rag_optional_sources": priority["optional"],
        "current_node": "route_rag",
    }
