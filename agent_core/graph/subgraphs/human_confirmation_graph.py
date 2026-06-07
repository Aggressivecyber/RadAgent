"""Human Confirmation Subgraph — multi-round user confirmation for model assumptions."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_core.human_confirmation.nodes import (
    HumanConfirmationState,
    build_proposed_model_completion,
    generate_confirmation_request,
    human_interrupt_node,
    merge_user_confirmation,
    parse_confirmation_response,
    validate_confirmation_completeness,
)


def route_after_merge(state: HumanConfirmationState) -> str:
    """Route after merging user confirmation — uses confirmation_status, NOT user_decision."""
    status = state.get("confirmation_status", "")

    if status == "ask_more":
        return "generate_confirmation_request"

    if status in {"approved", "edited", "pending"}:
        return "validate_confirmation_completeness"

    # rejected, failed, expired → END
    return END


def route_after_validate(state: HumanConfirmationState) -> str:
    """Route after validation — uses confirmation_status."""
    status = state.get("confirmation_status", "")
    if status == "pending":
        return "generate_confirmation_request"
    return END


def _route_after_interrupt(state: HumanConfirmationState) -> str:
    """Route after human interrupt — only proceed to parse if user responded."""
    return "parse_confirmation_response" if state.get("confirmation_status") == "received" else END


def build_human_confirmation_subgraph() -> StateGraph:
    """Build the Human Confirmation Subgraph."""
    graph = StateGraph(HumanConfirmationState)

    graph.add_node("build_proposed_model_completion", build_proposed_model_completion)
    graph.add_node("generate_confirmation_request", generate_confirmation_request)
    graph.add_node("human_interrupt_node", human_interrupt_node)
    graph.add_node("parse_confirmation_response", parse_confirmation_response)
    graph.add_node("merge_user_confirmation", merge_user_confirmation)
    graph.add_node("validate_confirmation_completeness", validate_confirmation_completeness)

    graph.set_entry_point("build_proposed_model_completion")
    graph.add_edge("build_proposed_model_completion", "generate_confirmation_request")
    graph.add_edge("generate_confirmation_request", "human_interrupt_node")

    # interrupt → only proceed to parse if status is "received" (user responded)
    # if pending, subgraph ends (main graph handles re-entry)
    graph.add_conditional_edges("human_interrupt_node", _route_after_interrupt)
    graph.add_edge("parse_confirmation_response", "merge_user_confirmation")

    graph.add_conditional_edges("merge_user_confirmation", route_after_merge)
    graph.add_conditional_edges("validate_confirmation_completeness", route_after_validate)

    return graph.compile()
