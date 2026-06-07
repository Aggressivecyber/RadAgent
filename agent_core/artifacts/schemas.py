"""Artifact Subgraph schemas."""

from __future__ import annotations

from typing import TypedDict


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

    # Output
    review_artifact_dir: str
    artifact_manifest_path: str
    artifact_status: str

    current_node: str
    errors: list[str]
