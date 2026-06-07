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


def route_after_parse(state: HumanConfirmationState) -> str:
    """Route after parsing user response."""
    decision = state.get("user_decision", "")
    if decision == "ask_more":
        return "generate_confirmation_request"
    if decision in ("approved", "edited"):
        return "validate_confirmation_completeness"
    # reject → END
    return END


def route_after_validate(state: HumanConfirmationState) -> str:
    """Route after validation."""
    status = state.get("confirmation_status", "")
    if status == "pending":
        return "generate_confirmation_request"
    return END


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
    graph.add_edge("human_interrupt_node", "parse_confirmation_response")
    graph.add_edge("parse_confirmation_response", "merge_user_confirmation")

    graph.add_conditional_edges("merge_user_confirmation", route_after_parse)
    graph.add_conditional_edges("validate_confirmation_completeness", route_after_validate)

    return graph
