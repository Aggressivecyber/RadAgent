"""Task Planning Subgraph — converts user query to task spec."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import parse_task, save_task_spec, validate_task_spec
from .schemas import TaskPlanningState

_MAX_RETRIES = 3


def _route_after_validation(state: TaskPlanningState) -> str:
    """Route based on validation result.

    Retries parse_task up to _MAX_RETRIES times on errors, then
    falls through to save_task_spec so the pipeline can continue
    (even with an incomplete spec) instead of looping forever.
    """
    errors = state.get("task_spec_errors", [])
    retry_count = state.get("_parse_retry_count", 0)
    if errors and retry_count < _MAX_RETRIES:
        return "parse_task"  # Retry
    return "save_task_spec"


def build_task_planning_subgraph() -> StateGraph:
    """Build the Task Planning Subgraph.

    Flow:
        parse_task → validate_task_spec → save_task_spec
                                       ↺ parse_task (on errors, max 3 retries)
    """
    graph = StateGraph(TaskPlanningState)

    graph.add_node("parse_task", parse_task)
    graph.add_node("validate_task_spec", validate_task_spec)
    graph.add_node("save_task_spec", save_task_spec)

    graph.set_entry_point("parse_task")
    graph.add_edge("parse_task", "validate_task_spec")

    graph.add_conditional_edges(
        "validate_task_spec",
        _route_after_validation,
        {
            "save_task_spec": "save_task_spec",
            "parse_task": "parse_task",
        },
    )

    graph.add_edge("save_task_spec", END)

    return graph
