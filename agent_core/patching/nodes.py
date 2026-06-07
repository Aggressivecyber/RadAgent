"""Patch Subgraph nodes — review, apply, and verify code patches.

Uses JSON replacement patch format. Codegen nodes never write directly
to the final project — patches must go through this subgraph.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from agent_core.config.workspace import get_job_dir
from agent_core.validators.file_permission_validator import FilePermissionValidator
from agent_core.validators.patch_validator import PatchValidator

from .schemas import PatchSubgraphState


async def load_proposed_patch(state: PatchSubgraphState) -> dict[str, Any]:
    """Load proposed patch from file."""
    patch_path = state.get("proposed_patch_path", "")
    if patch_path and Path(patch_path).exists():
        patch = json.loads(Path(patch_path).read_text())
    else:
        patch = {}
    return {"proposed_patch": patch}


async def review_patch(state: PatchSubgraphState) -> dict[str, Any]:
    """Review patch format and file permissions."""
    patch = state.get("proposed_patch", {})
    job_id = state.get("job_id", "unknown")
    job_dir = get_job_dir(job_id)
    val_dir = job_dir / "09_validation"
    val_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    # Format validation
    pv = PatchValidator()
    fmt_valid, fmt_errors = pv.validate_patch_format(patch)
    if not fmt_valid:
        errors.extend(fmt_errors)

    # Permission validation
    fpv = FilePermissionValidator()
    changed_files = patch.get("changed_files", [])
    perm_valid, perm_msgs = fpv.validate_patch_permissions(changed_files)
    if not perm_valid:
        errors.extend(perm_msgs)

    review = {
        "format_valid": fmt_valid,
        "permission_valid": perm_valid,
        "errors": errors,
        "reviewed_at": datetime.now(UTC).isoformat(),
    }

    review_path = val_dir / "patch_review.json"
    review_path.write_text(json.dumps(review, indent=2, ensure_ascii=False))

    return {
        "patch_review_result": review,
        "patch_review_path": str(review_path),
        "errors": errors,
    }


async def apply_patch(state: PatchSubgraphState) -> dict[str, Any]:
    """Apply the reviewed patch to the generated code directory."""
    patch = state.get("proposed_patch", {})
    review = state.get("patch_review_result", {})
    code_dir = state.get("generated_code_dir", "")
    job_id = state.get("job_id", "unknown")
    job_dir = get_job_dir(job_id)

    errors = list(state.get("errors", []))

    # Don't apply if review failed
    if review.get("errors"):
        return {
            "patch_status": "rejected",
            "errors": errors + ["Patch rejected due to review errors"],
        }

    if not code_dir or not Path(code_dir).exists():
        return {
            "patch_status": "failed",
            "errors": errors + [f"Code directory not found: {code_dir}"],
        }

    applied_files: list[str] = []
    changed_files = patch.get("changed_files", [])

    for file_entry in changed_files:
        if not isinstance(file_entry, dict):
            continue
        path = file_entry.get("path", "")
        content = file_entry.get("new_content")

        # Backward compat: deprecated 'content' field
        if content is None and "content" in file_entry:
            logger.warning(
                "Deprecated patch field 'content' used for: %s. "
                "Use 'new_content' instead.",
                path,
            )
            content = file_entry["content"]

        if not path:
            continue
        if content is None:
            errors.append(f"Patch file entry missing new_content: {path}")
            continue

        # Security: prevent path traversal
        if ".." in path or path.startswith("/"):
            errors.append(f"Rejected path traversal: {path}")
            continue

        target = Path(code_dir) / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        applied_files.append(path)

    applied_at = datetime.now(UTC).isoformat()

    # Save applied patch record
    applied_record = {
        "job_id": job_id,
        "applied_at": applied_at,
        "files_applied": applied_files,
        "files_count": len(applied_files),
    }
    applied_path = job_dir / "09_validation" / "applied_patch.json"
    applied_path.parent.mkdir(parents=True, exist_ok=True)
    applied_path.write_text(json.dumps(applied_record, indent=2, ensure_ascii=False))

    status = "applied" if applied_files else "failed"

    return {
        "applied_patch_path": str(applied_path),
        "patch_applied_at": applied_at,
        "patch_status": status,
        "errors": errors,
    }
