"""Patch Subgraph schemas."""

from __future__ import annotations

from typing import Any, TypedDict


class PatchSubgraphState(TypedDict, total=False):
    """State for the Patch Subgraph."""

    job_id: str
    proposed_patch_path: str
    generated_code_dir: str

    # Loaded data
    proposed_patch: dict[str, Any]

    # Review results
    patch_review_result: dict[str, Any]

    # Output
    patch_review_path: str
    applied_patch_path: str
    patch_applied_at: str
    patch_status: str  # "applied" | "rejected" | "failed"

    current_node: str
    errors: list[str]
