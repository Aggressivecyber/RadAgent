"""Generate fix patch based on failure analysis."""

from __future__ import annotations

import uuid

from agent_core.graph.state import RadiationAgentState


async def write_fix_patch(state: RadiationAgentState) -> dict:
    """Generate a fix patch based on the failure report and error context."""
    failure = state.get("failure_report", {})
    job_id = state.get("job_id", "unknown")
    patch = state.get("proposed_patch", {})
    error_context = state.get("web_context", [])

    fix = {
        "patch_id": str(uuid.uuid4()),
        "job_id": job_id,
        "description": f"Fix for {failure.get('gate_name', 'unknown')}: {failure.get('message', '')}",
        "change_type": "modify",
        "risk_level": "medium",
        "changed_files": patch.get("changed_files", []),
        "fix_reason": failure.get("message", ""),
        "retry_count": state.get("retry_count", 0),
        "error_context_used": bool(error_context),
    }

    return {"fix_patch": fix, "current_node": "write_fix_patch"}
