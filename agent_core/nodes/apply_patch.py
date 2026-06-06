"""Apply code patch to filesystem.

Fix 2: The SOLE node that writes actual simulation code files.
        workspace_root is set to the job directory so that relative
        paths in the patch (e.g. 05_geant4/src/Foo.cc) resolve correctly.
"""

from __future__ import annotations

import json

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState
from agent_core.tools.patch_tool import PatchTool


async def apply_patch(state: RadiationAgentState) -> dict:
    """Apply the reviewed code patch to the filesystem.

    Prerequisites: review_code_patch must have passed (overall_valid=True).
    """
    patch = state.get("proposed_patch", {})
    review = state.get("patch_review_result", {})
    job_id = state.get("job_id", "unknown")

    if not patch.get("changed_files"):
        return {
            "applied_patch": {"applied": False, "reason": "Empty patch"},
            "current_node": "apply_patch",
            "errors": ["No files in proposed patch"],
        }

    if not review.get("overall_valid", False):
        return {
            "applied_patch": {"applied": False, "reason": "Patch review failed"},
            "current_node": "apply_patch",
            "errors": ["Patch review did not pass: " + json.dumps(review)],
        }

    # Fix 2: workspace_root = job_dir so relative paths in patch resolve correctly
    # e.g. "05_geant4/src/DetectorConstruction.cc" → job_dir/05_geant4/src/...
    job_dir = str(get_job_dir(job_id))
    tool = PatchTool(job_dir)
    result = tool.apply_patch(patch)

    return {"applied_patch": result, "current_node": "apply_patch"}
