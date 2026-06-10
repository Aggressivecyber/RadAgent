"""Patch subgraph builder."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_core.patching.nodes import apply_patch, load_proposed_patch, review_patch
from agent_core.patching.schemas import PatchSubgraphState


def build_patch_subgraph() -> StateGraph:
    """Build the Patch Subgraph."""
    graph = StateGraph(PatchSubgraphState)

    graph.add_node("load_proposed_patch", load_proposed_patch)
    graph.add_node("review_patch", review_patch)
    graph.add_node("apply_patch", apply_patch)

    graph.set_entry_point("load_proposed_patch")
    graph.add_edge("load_proposed_patch", "review_patch")
    graph.add_edge("review_patch", "apply_patch")
    graph.add_edge("apply_patch", END)
    return graph
