"""Main graph state for RadAgent — lightweight orchestration state.

The main state holds ONLY paths and status strings. Large data objects
(g4_model_ir, component_specs, rag_context, etc.) are persisted to disk
and referenced by path. Subgraphs manage their own detailed state internally.

This follows the principle: "Main graph only schedules, never processes."
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def _last_value(existing: Any, new: Any) -> Any:
    """Reducer: last-write-wins for concurrent updates."""
    return new


class RadAgentMainState(TypedDict, total=False):
    """Lightweight orchestration state for the main graph.

    All subgraph outputs are referenced by file paths, not inlined.
    The main graph never holds geometry details, C++ code, or
    artifact content directly.
    """

    # ── Job identification ──
    job_id: str
    user_query: str
    execution_mode: str  # "strict" | "test" | "acceptance" | "production"
    run_mode: str  # "strict" | "test" | "acceptance" | "production"

    # ── Intent Router outputs ──
    intent: str  # IntentType from intent/schemas.py
    intent_detail: str  # Fine-grained routing detail under the two top-level intents
    intent_confidence: float
    intent_routing_reason: str
    normalized_user_query: str
    requires_job: bool
    requires_simulation_pipeline: bool
    requires_clarification: bool

    # ── Response (for non-simulation intents) ──
    response_text: str
    response_status: str  # "answered" | "needs_clarification"
    pipeline_terminated: bool

    # ── Workspace ──
    workspace_root: str  # Path to workspace root directory
    job_workspace: str  # Path to job root directory

    # ── Context Subgraph outputs ──
    context_decision: str  # "allow_rag" | "allow_with_web_supplement" | "block_no_context"
    context_report_path: str
    evidence_map_path: str

    # ── Task Planning Subgraph outputs ──
    task_spec_path: str
    simulation_scope: list[str]
    task_planning_status: str  # "passed" | "failed" | "reserved"

    # ── Requirements Review outputs ──
    requirements_review_status: str  # "pending" | "approved" | "rejected" | "failed"
    requirements_review_request_path: str
    requirements_review_response_path: str
    confirmed_requirement_plan_path: str

    # ── G4 Modeling Subgraph outputs ──
    g4_model_ir_path: str
    component_specs_dir: str
    interfaces_path: str
    construction_ledger_path: str
    model_review_report_path: str
    g4_modeling_status: str  # "passed" | "failed" | "needs_user_input"

    # ── Human Confirmation Subgraph outputs ──
    confirmation_status: str  # "not_required"|"pending"|"approved"|"edited"|"rejected"|"ask_more"|"expired"|"failed"  # noqa: E501
    confirmation_request_path: str
    confirmation_response_path: str
    confirmation_record_path: str
    confirmed_model_plan_path: str
    unconfirmed_assumptions_count: int
    human_confirmation_required: bool
    human_confirmation_round: int
    raw_human_response: dict[str, Any]  # Raw response from human
    confirmation_report_path: str  # Path to confirmation report
    human_confirmation_edited_fields: list[str]  # Fields edited by user

    # ── G4 Codegen Subgraph outputs ──
    code_module_plan_path: str
    proposed_patch_path: str
    generated_code_dir: str
    g4_codegen_status: str  # "passed" | "failed" | "needs_user_input"
    repair_continuation_request: dict[str, Any]
    repair_continuation_status: str  # "pending" | "approved" | "rejected"
    agentic_repair_max_turns_override: int

    # ── Patch Subgraph outputs ──
    patch_review_path: str
    applied_patch_path: str
    patch_applied_at: str
    patch_status: str  # "applied" | "rejected" | "failed"

    # ── Gate Subgraph outputs ──
    gate_results_path: str
    validation_status: str  # "passed" | "failed" | "blocked"
    failed_gates: list[str]
    skipped_gates: list[str]

    # ── Artifact Subgraph outputs ──
    review_artifact_dir: str
    artifact_manifest_path: str
    artifact_status: str  # "collected" | "failed"

    # ── Report Subgraph outputs ──
    final_report_path: str
    verified: bool
    termination_reason: str

    # ── Control flow ──
    retry_count: Annotated[int, _last_value]
    max_retries_reached: Annotated[bool, _last_value]
    current_node: Annotated[str, _last_value]
    errors: list[str]
