"""Gate Validation Subgraph schemas."""

from __future__ import annotations

from typing import Any, TypedDict


class GateSubgraphState(TypedDict, total=False):
    """State for the Gate Validation Subgraph."""

    # Input
    job_id: str
    execution_mode: str  # "dev_no_geant4_env" | "mvp1_acceptance"
    g4_model_ir_path: str
    generated_code_dir: str
    applied_patch_path: str
    patch_applied_at: str
    task_spec_path: str
    context_decision: str
    retry_count: int

    # Loaded data
    g4_model_ir: dict[str, Any]
    task_spec: dict[str, Any]
    code_modules: list[dict[str, Any]]

    # Results
    gate_results: list[dict[str, Any]]
    gate_results_path: str
    validation_status: str  # "VERIFIED" | "FAILED" | "PARTIAL"
    failed_gates: list[str]
    skipped_gates: list[str]

    current_node: str
    errors: list[str]
