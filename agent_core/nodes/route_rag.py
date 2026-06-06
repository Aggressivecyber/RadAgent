"""RAG routing node."""

from __future__ import annotations

import json
from pathlib import Path

from agent_core.graph.state import RadiationAgentState
from agent_core.tools.rag_router import RAGRouter


async def route_rag(state: RadiationAgentState) -> dict:
    """Determine which RAG sources to query based on task spec."""
    task_spec = state.get("task_spec", {})
    job_id = state.get("job_id", "unknown")

    router = RAGRouter()
    rag_route = router.route(task_spec)

    # Save routing decision
    job_dir = Path("simulation_workspace/jobs") / job_id
    route_file = job_dir / "01_context" / "rag_route.json"
    route_file.write_text(
        json.dumps(
            {"rag_route": rag_route, "task_scope": task_spec.get("simulation_scope", [])},
            indent=2,
        )
    )

    return {"rag_route": rag_route, "current_node": "route_rag"}
