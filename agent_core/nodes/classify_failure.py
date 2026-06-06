"""Classify gate check failures."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


async def classify_failure(state: RadiationAgentState) -> dict:
    """Classify the type of failure from gate check results."""
    gate_results = state.get("gate_results", [])
    retry_count = state.get("retry_count", 0) + 1

    # Find first failed gate
    failed_gates = [g for g in gate_results if g.get("severity") in ("fail", "block")]

    if not failed_gates:
        return {
            "failure_report": {"type": "none", "message": "No failures"},
            "retry_count": retry_count,
            "current_node": "classify_failure",
        }

    first_failure = failed_gates[0]
    gate_id = first_failure.get("gate_id", -1)
    gate_name = first_failure.get("gate_name", "unknown")

    # Classify failure type
    failure_type = "unknown"
    if gate_id == 0:
        failure_type = "rag_insufficient"
    elif gate_id in (1, 2):
        failure_type = "schema_invalid"
    elif gate_id == 3:
        failure_type = "patch_format_error"
    elif gate_id == 4:
        failure_type = "permission_violation"
    elif gate_id in (5, 6):
        failure_type = "build_error"
    elif gate_id == 7:
        failure_type = "test_failure"
    elif gate_id == 8:
        failure_type = "contract_violation"
    elif gate_id in (9, 10, 11):
        failure_type = "runtime_error"

    failure_report = {
        "type": failure_type,
        "gate_id": gate_id,
        "gate_name": gate_name,
        "message": first_failure.get("message", ""),
        "retry_node": first_failure.get("retry_node"),
        "total_retries": retry_count,
    }

    return {
        "failure_report": failure_report,
        "retry_count": retry_count,
        "max_retries_reached": retry_count >= 20,
        "current_node": "classify_failure",
    }
