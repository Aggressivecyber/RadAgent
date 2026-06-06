"""Parse user request node for LangGraph."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from agent_core.graph.state import RadiationAgentState


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
    workspace_root = Path("simulation_workspace/jobs")
    job_dir = workspace_root / job_id
    dirs_to_create = [
        job_dir / "00_request",
        job_dir / "01_context",
        job_dir / "02_task_spec",
        job_dir / "03_simulation_ir",
        job_dir / "04_generated_code",
        job_dir / "05_geant4" / "src",
        job_dir / "05_geant4" / "include",
        job_dir / "05_geant4" / "macros",
        job_dir / "08_data_packages" / "g4_output_package",
        job_dir / "09_validation",
        job_dir / "10_report",
    ]
    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    # Save user query
    query_file = job_dir / "00_request" / "user_query.md"
    query_file.write_text(f"# User Request\n\n{user_query}\n")

    return {
        "job_id": job_id,
        "user_query": user_query,
        "current_node": "parse_user_request",
        "errors": [],
    }
