"""Main graph routing logic for RadAgent orchestration.

All routing decisions are based on lightweight status strings and paths
in the main state — never on detailed domain content.
"""

from __future__ import annotations

from agent_core.gates.failure_classifier import classify_failed_gates
from agent_core.graph.main_state import RadAgentMainState


def route_after_intent(state: RadAgentMainState) -> str:
    """Route after Intent Router based on classified intent."""
    intent = state.get("intent", "chat")
    intent_detail = state.get("intent_detail", "")

    if intent == "chat":
        return "chat_response_node"

    if intent == "simulation_work" and intent_detail == "human_confirmation_response":
        return "human_confirmation_subgraph"

    if intent == "simulation_work":
        return "prepare_workspace"

    return "chat_response_node"


def route_after_context(state: RadAgentMainState) -> str:
    """Route after Context Subgraph based on context sufficiency."""
    decision = state.get("context_decision", "block_no_context")
    if decision in ("allow_rag", "allow_with_web_supplement"):
        return "task_planning_subgraph"
    return "report_subgraph"


def route_after_task_planning(state: RadAgentMainState) -> str:
    """Route after Task Planning Subgraph.

    Only "geant4" scope proceeds to G4 Modeling.
    TCAD/SPICE/full_chain scopes are BLOCKED — routed to report_subgraph
    with a clear message that these scopes are reserved for future phases.
    """
    status = state.get("task_planning_status", "failed")

    # Reserved scope (TCAD/SPICE/full_chain) → report immediately
    if status == "reserved":
        return "report_subgraph"

    if status == "failed":
        return "report_subgraph"

    scope = state.get("simulation_scope", [])

    # HARD BLOCK: any non-geant4 scope → report_subgraph
    reserved_scopes = {"tcad", "spice", "geant4_to_tcad", "tcad_to_spice", "full_chain"}
    if any(s in reserved_scopes for s in scope):
        # Do NOT enter g4_modeling or g4_codegen
        return "report_subgraph"

    # Only pure geant4 scope proceeds
    if scope == ["geant4"]:
        return "g4_modeling_subgraph"

    # Unknown/empty scope → report
    return "report_subgraph"


def route_after_g4_modeling(state: RadAgentMainState) -> str:
    """Route after G4 Modeling Subgraph.

    Check if human confirmation is required before proceeding to codegen.
    """
    status = state.get("g4_modeling_status", "failed")
    if status == "passed":
        # Check if human confirmation is required
        hc_required = state.get("human_confirmation_required", False)
        if hc_required:
            return "human_confirmation_subgraph"
        return "g4_codegen_subgraph"
    if status == "needs_user_input":
        return "report_subgraph"
    return "report_subgraph"


def route_after_human_confirmation(state: RadAgentMainState) -> str:
    """Route after Human Confirmation Subgraph.

    Only proceed to codegen when confirmation is complete:
    - status is approved/edited
    - confirmation_record_path exists
    - confirmed_model_plan_path exists
    - unconfirmed_assumptions_count == 0
    """
    status = state.get("confirmation_status", "failed")
    modeling_status = state.get("g4_modeling_status")

    if status in {"approved", "edited"}:
        if modeling_status and modeling_status != "passed":
            return "report_subgraph"
        if state.get("unconfirmed_assumptions_count", 0) > 0:
            return "report_subgraph"
        if not state.get("confirmation_record_path"):
            return "report_subgraph"
        if not state.get("confirmed_model_plan_path"):
            return "report_subgraph"
        return "g4_codegen_subgraph"

    if status == "ask_more":
        return "context_subgraph"

    if status == "pending":
        return "report_subgraph"

    # rejected, failed, expired, or unknown
    return "report_subgraph"


def route_after_g4_codegen(state: RadAgentMainState) -> str:
    """Route after G4 Codegen Subgraph."""
    status = state.get("g4_codegen_status", "failed")
    if status == "passed":
        return "patch_subgraph"
    return "report_subgraph"


def route_after_patch(state: RadAgentMainState) -> str:
    """Route after Patch Subgraph."""
    status = state.get("patch_status", "failed")
    if status == "applied":
        return "gate_subgraph"
    return "report_subgraph"


def route_after_gates(state: RadAgentMainState) -> str:
    """Route after Gate Validation Subgraph.

    On failure with retries remaining, route back to the appropriate
    subgraph based on the failed gate type.
    """
    failed_gates = _active_failed_gates(state.get("failed_gates", []))
    validation_status = state.get("validation_status", "failed")
    if validation_status in {"failed", "blocked"} and not failed_gates:
        return "artifact_subgraph"
    if validation_status == "passed":
        return "artifact_subgraph"

    # Check retry limit
    retry_count = state.get("retry_count", 0)
    if retry_count >= 5:
        return "report_subgraph"

    # Route back based on which gates failed
    return classify_failed_gates(failed_gates)


def route_after_artifact(state: RadAgentMainState) -> str:
    """Route after Artifact Subgraph — always goes to report."""
    return "report_subgraph"


def _active_failed_gates(failed_gates: object) -> list[object]:
    if not isinstance(failed_gates, list):
        return []
    return [gate for gate in failed_gates if not _is_retired_visual_review_gate(gate)]


def _is_retired_visual_review_gate(gate: object) -> bool:
    if isinstance(gate, dict):
        try:
            return int(gate.get("gate_id", -1)) == 21
        except (TypeError, ValueError):
            return False
    return str(gate).strip() == "G4 Visual Review"
