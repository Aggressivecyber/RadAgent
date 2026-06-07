"""Patch Subgraph — review and apply code patches."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import apply_patch, load_proposed_patch, review_patch
from .schemas import PatchSubgraphState


def _route_after_review(state: PatchSubgraphState) -> str:
    """Apply only if review passed."""
    errors = state.get("errors", [])
    if errors:
        return "apply_patch"  # Will mark as rejected
    return "apply_patch"


def build_patch_subgraph() -> StateGraph:
    """Build the Patch Subgraph.

    Flow: load_patch → review_patch → apply_patch
    """
    graph = StateGraph(PatchSubgraphState)

    graph.add_node("load_proposed_patch", load_proposed_patch)
    graph.add_node("review_patch", review_patch)
    graph.add_node("apply_patch", apply_patch)

    graph.set_entry_point("load_proposed_patch")
    graph.add_edge("load_proposed_patch", "review_patch")
    graph.add_edge("review_patch", "apply_patch")
    graph.add_edge("apply_patch", END)

    return graph
