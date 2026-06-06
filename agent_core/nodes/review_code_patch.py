"""Review generated code patch."""

from __future__ import annotations

import json

from agent_core.graph.state import RadiationAgentState
from agent_core.validators.file_permission_validator import FilePermissionValidator
from agent_core.validators.patch_validator import PatchValidator


async def review_code_patch(state: RadiationAgentState) -> dict:
    """Review the proposed code patch for format and permission issues."""
    patch = state.get("proposed_patch", {})
    pv = PatchValidator()
    fpv = FilePermissionValidator()

    # Validate patch format
    format_valid, format_errors = pv.validate_patch_format(patch)

    # Validate file permissions
    changed_files = patch.get("changed_files", [])
    perm_valid, perm_messages = fpv.validate_patch_permissions(changed_files)

    # Validate diff syntax for each file
    diff_errors = []
    for cf in changed_files:
        diff = cf.get("diff_content", "")
        if diff:
            ok, err = pv.validate_diff_syntax(diff)
            if not ok:
                diff_errors.append(f"{cf.get('path')}: {err}")

    all_valid = format_valid and perm_valid and not diff_errors
    review = {
        "format_valid": format_valid,
        "permission_valid": perm_valid,
        "diff_errors": diff_errors,
        "format_errors": format_errors,
        "permission_messages": perm_messages,
        "overall_valid": all_valid,
    }

    return {"patch_review_result": review, "current_node": "review_code_patch"}
