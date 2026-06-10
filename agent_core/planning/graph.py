"""Task planning subgraph builder."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_core.planning.nodes import parse_task, save_task_spec, validate_task_spec
from agent_core.planning.schemas import TaskPlanningState

_MAX_RETRIES = 3


def _route_after_validation(state: TaskPlanningState) -> str:
    """Retry parsing on validation errors, then persist the latest task spec."""
    errors = state.get("task_spec_errors", [])
    retry_count = state.get("_parse_retry_count", 0)
    if errors and retry_count < _MAX_RETRIES:
        return "parse_task"
    return "save_task_spec"


def build_task_planning_subgraph() -> StateGraph:
    """Build the Task Planning Subgraph."""
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
