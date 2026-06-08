"""Main graph routing logic for RadAgent orchestration.

All routing decisions are based on lightweight status strings and paths
in the main state — never on detailed domain content.
"""

from __future__ import annotations

from agent_core.graph.main_state import RadAgentMainState


def route_after_intent(state: RadAgentMainState) -> str:
    """Route after Intent Router based on classified intent."""
    intent = state.get("intent", "unknown")

    if intent == "smalltalk":
        return "chat_response_node"

    if intent == "help":
        return "help_response_node"

    if intent == "status_query":
        return "status_response_node"

    if intent == "capability_query":
        return "capability_response_node"

    if intent == "human_confirmation_response":
        return "human_confirmation_subgraph"

    if intent in {"simulation_request", "simulation_edit", "simulation_continue"}:
        return "prepare_workspace"

    if intent == "artifact_query":
        return "status_response_node"

    return "clarification_node"


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
    with a clear message that these are reserved for later MVP phases.
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

    if status in {"approved", "edited"}:
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
        return "human_confirmation_subgraph"

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
    validation_status = state.get("validation_status", "failed")
    if validation_status == "passed":
        return "artifact_subgraph"

    # Check retry limit
    retry_count = state.get("retry_count", 0)
    if retry_count >= 5:
        return "report_subgraph"

    # Route back based on which gates failed
    failed_gates = state.get("failed_gates", [])
    return _route_by_failed_gates(failed_gates)


def _route_by_failed_gates(failed_gates: list[str]) -> str:
    """Determine retry target based on which gates failed."""
    if not failed_gates:
        return "report_subgraph"

    # Context gates → back to context
    context_gates = {"Gate 0", "G4-E"}
    if any(g in context_gates for g in failed_gates):
        return "context_subgraph"

    # Task spec gates → back to task planning
    task_gates = {"Gate 1"}
    if any(g in task_gates for g in failed_gates):
        return "task_planning_subgraph"

    # Modeling gates → back to G4 modeling
    modeling_gates = {"Gate 2", "G4-A", "G4-B", "G4-C", "G4-D"}
    if any(g in modeling_gates for g in failed_gates):
        return "g4_modeling_subgraph"

    # Codegen/build gates → back to G4 codegen
    codegen_gates = {"Gate 5", "Gate 6", "Gate 7", "G4-F", "G4-G"}
    if any(g in codegen_gates for g in failed_gates):
        return "g4_codegen_subgraph"

    # Patch gates → back to patch
    patch_gates = {"Gate 3", "Gate 4"}
    if any(g in patch_gates for g in failed_gates):
        return "patch_subgraph"

    # Default: back to gate subgraph for re-check
    return "report_subgraph"


def route_after_artifact(state: RadAgentMainState) -> str:
    """Route after Artifact Subgraph — always goes to report."""
    return "report_subgraph"
