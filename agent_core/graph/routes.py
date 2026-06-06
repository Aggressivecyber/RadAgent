"""Routing logic for LangGraph conditional edges."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


def route_after_rag(state: RadiationAgentState) -> str:
    """After RAG retrieval, route based on sufficiency score."""
    score = state.get("rag_sufficiency_score", 0.0)
    if score < 0.60:
        return "retrieve_error_context"
    return "plan_simulation"


def route_after_gate_checks(state: RadiationAgentState) -> str:
    """After gate checks, route based on results."""
    gate_results = state.get("gate_results", [])
    all_passed = all(
        r.get("severity") in ("pass", "warning") for r in gate_results
    )
    if all_passed:
        return "parse_simulation_results"
    return "classify_failure"


def route_after_task_spec_validation(state: RadiationAgentState) -> str:
    """Route based on task spec validation."""
    errors = state.get("task_spec_errors", [])
    retry_count = state.get("retry_count", 0)
    # Safety valve: after 3 retries, force proceed even with errors
    if errors and retry_count < 3:
        return "build_task_spec"
    return "build_simulation_ir"


def route_after_sim_ir_validation(state: RadiationAgentState) -> str:
    """Route based on simulation IR validation."""
    errors = state.get("simulation_ir_errors", [])
    retry_count = state.get("retry_count", 0)
    if errors and retry_count < 3:
        return "build_simulation_ir"
    return "route_rag"


def route_after_classify_failure(state: RadiationAgentState) -> str:
    """Route based on failure classification."""
    retry_count = state.get("retry_count", 0)
    if retry_count >= 5:
        return "generate_report"  # Give up after 5 retries, still generate report
    failure = state.get("failure_report", {})
    failure_type = failure.get("type", "unknown")
    if failure_type in ("rag_insufficient",):
        # RAG insufficiency that persisted through retry → proceed with warning
        return "generate_report"
    if failure_type in ("schema_invalid",):
        return "retrieve_error_context"
    if failure_type in ("build_error", "runtime_error", "test_failure", "patch_format_error"):
        return "write_fix_patch"
    if failure_type in ("permission_violation",):
        return "generate_report"  # Can't fix permission violations automatically
    return "retrieve_error_context"
