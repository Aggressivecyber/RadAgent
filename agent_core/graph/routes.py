"""Routing logic for LangGraph conditional edges."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


def route_after_rag(state: RadiationAgentState) -> str:
    """After RAG sufficiency scoring, route based on context decision.

    - allow_rag:         RAG is sufficient → proceed to plan.
    - needs_web:         RAG is partial → try web search.
    - block_no_context:  RAG is empty/terrible → terminate.
    """
    decision = state.get("context_decision", "block_no_context")
    if decision == "allow_rag":
        return "plan_simulation"
    if decision == "needs_web":
        return "retrieve_web_context"
    return "generate_report"  # TERMINATE


def route_after_combined_context(state: RadiationAgentState) -> str:
    """After combined RAG+Web scoring, route based on final decision."""
    decision = state.get("context_decision", "block_no_context")
    if decision in ("allow_rag", "allow_with_web_supplement"):
        return "plan_simulation"
    return "generate_report"  # TERMINATE


def route_after_gate_checks(state: RadiationAgentState) -> str:
    """After gate checks, route based on results.

    In mvp1_acceptance mode, critical gates (6/8/9/11) cannot be skipped —
    a skipped critical gate routes to classify_failure.
    In dev_no_geant4_env mode, skipped gates are tolerated.
    """
    gate_results = state.get("gate_results", [])
    execution_mode = state.get("execution_mode", "dev_no_geant4_env")

    # Check for hard failures (fail/block severity)
    has_hard_failure = any(
        r.get("severity") in ("fail", "block") for r in gate_results
    )
    if has_hard_failure:
        return "classify_failure"

    # MVP-1 acceptance: critical gates 6/8/9/11 skipped = failure
    if execution_mode == "mvp1_acceptance":
        critical_skipped = [
            r for r in gate_results
            if r.get("severity") == "skipped" and r.get("gate_id") in (6, 8, 9, 11)
        ]
        if critical_skipped:
            return "classify_failure"

    # All pass, warning, or non-critical skip
    return "parse_simulation_results"


def route_after_task_spec_validation(state: RadiationAgentState) -> str:
    """Route based on task spec validation.

    After 3 retries with errors, stop and generate report — do NOT force proceed.
    """
    errors = state.get("task_spec_errors", [])
    retry_count = state.get("retry_count", 0)
    if errors and retry_count < 3:
        return "build_task_spec"
    if errors and retry_count >= 3:
        return "generate_report"
    return "build_simulation_ir"


def route_after_sim_ir_validation(state: RadiationAgentState) -> str:
    """Route based on simulation IR validation.

    After 3 retries with errors, stop and generate report — do NOT force proceed.
    """
    errors = state.get("simulation_ir_errors", [])
    retry_count = state.get("retry_count", 0)
    if errors and retry_count < 3:
        return "build_simulation_ir"
    if errors and retry_count >= 3:
        return "generate_report"
    return "route_rag"


def route_after_classify_failure(state: RadiationAgentState) -> str:
    """Route based on failure classification."""
    retry_count = state.get("retry_count", 0)
    if retry_count >= 5:
        return "generate_report"
    failure = state.get("failure_report", {})
    failure_type = failure.get("type", "unknown")
    if failure_type in ("rag_insufficient",):
        return "generate_report"
    if failure_type in ("schema_invalid",):
        return "retrieve_error_context"
    if failure_type in ("build_error", "runtime_error", "test_failure", "patch_format_error"):
        return "write_fix_patch"
    if failure_type in ("permission_violation",):
        return "generate_report"
    return "retrieve_error_context"
