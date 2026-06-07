"""Report Subgraph schemas."""

from __future__ import annotations

from typing import TypedDict


class ReportSubgraphState(TypedDict, total=False):
    """State for the Report Generation Subgraph."""

    job_id: str
    user_query: str
    execution_mode: str
    context_decision: str
    validation_status: str
    g4_model_ir_path: str
    gate_results_path: str
    model_review_report_path: str
    simulation_scope: list[str]
    failed_gates: list[str]
    errors: list[str]

    final_report_path: str
    verified: bool
    termination_reason: str
