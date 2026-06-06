"""Parse user request node for LangGraph."""

from __future__ import annotations

import uuid
from datetime import datetime

from agent_core.config.workspace import ensure_job_dirs
from agent_core.graph.state import RadiationAgentState
from agent_core.tools.rag_discovery_tool import discover_rag_sources


async def parse_user_request(state: RadiationAgentState) -> dict:
    """Parse the user's natural language request.

    Creates job_id, saves user query, initializes workspace directories.
    """
    user_query = state.get("user_query", "")
    if not user_query:
        return {"errors": ["Empty user query"], "current_node": "parse_user_request"}

    job_id = (
        state.get("job_id")
        or f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    )

    # Create job workspace directories
    job_dir = ensure_job_dirs(job_id)

    # Save user query
    query_file = job_dir / "00_request" / "user_query.md"
    query_file.write_text(f"# User Request\n\n{user_query}\n")

    # Discover available RAG sources
    rag_registry = await discover_rag_sources()

    return {
        "job_id": job_id,
        "user_query": user_query,
        "rag_registry": rag_registry,
        "current_node": "parse_user_request",
        "errors": [],
    }
