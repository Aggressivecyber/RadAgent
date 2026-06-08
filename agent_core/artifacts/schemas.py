"""Artifact Subgraph schemas."""

from __future__ import annotations

from typing import Any, TypedDict


class ArtifactSubgraphState(TypedDict, total=False):
    """State for the Artifact Collection Subgraph."""

    # Input paths
    job_id: str
    gate_results_path: str
    g4_model_ir_path: str
    model_review_report_path: str
    construction_ledger_path: str
    code_module_plan_path: str
    proposed_patch_path: str
    validation_status: str

    # Runtime context
    execution_mode: str  # "strict", "test", "acceptance", or "production"
    gate_results: list[dict[str, Any]]  # Gate check results for skipped_gates extraction
    g4_model_ir: dict[str, Any]  # Direct Model IR data (alternative to path)

    # Output
    review_artifact_dir: str
    artifact_manifest_path: str
    artifact_status: str

    current_node: str
    errors: list[str]
