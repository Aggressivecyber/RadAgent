"""Apply code patch to filesystem."""

from __future__ import annotations

import json

from agent_core.graph.state import RadiationAgentState
from agent_core.tools.patch_tool import PatchTool


async def apply_patch(state: RadiationAgentState) -> dict:
    """Apply the reviewed code patch to the filesystem."""
    patch = state.get("proposed_patch", {})
    review = state.get("patch_review_result", {})

    if not review.get("overall_valid", False):
        return {
            "applied_patch": {"applied": False, "reason": "Patch review failed"},
            "current_node": "apply_patch",
            "errors": ["Patch review did not pass: " + json.dumps(review)],
        }

    workspace_root = "simulation_workspace"
    tool = PatchTool(workspace_root)
    result = tool.apply_patch(patch)

    return {"applied_patch": result, "current_node": "apply_patch"}
