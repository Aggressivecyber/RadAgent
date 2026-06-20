"""Task Planning subgraph schemas."""

from __future__ import annotations

from typing import Any, TypedDict


class TaskPlanningInput(TypedDict, total=False):
    """Input to the Task Planning Subgraph."""

    job_id: str
    user_query: str
    context_report_path: str
    evidence_map_path: str
    copilot_briefing: dict[str, Any]


class TaskPlanningOutput(TypedDict, total=False):
    """Output from the Task Planning Subgraph."""

    task_spec_path: str
    simulation_scope: list[str]
    task_planning_status: str  # "passed" | "failed" | "needs_user_input"
    task_spec_errors: list[str]
    termination_reason: str


class TaskPlanningState(TypedDict, total=False):
    """Internal state for Task Planning Subgraph."""

    job_id: str
    user_query: str
    context_report_path: str
    evidence_map_path: str
    copilot_briefing: dict[str, Any]

    # Parsed task
    task_spec: dict[str, Any]
    task_spec_errors: list[str]
    simulation_scope: list[str]
    clarification_request: dict[str, Any]
    termination_reason: str

    # Retry counter for parse_task loop
    _parse_retry_count: int

    # Output paths
    task_spec_path: str
    task_planning_status: str
