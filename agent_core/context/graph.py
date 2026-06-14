"""Context subgraph builder."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_core.context.nodes import (
    extract_user_context_requirements,
    retrieve_rag_context,
    retrieve_web_context,
    route_sources,
    save_evidence_map,
    score_combined_context,
    score_rag_context,
)
from agent_core.context.schemas import ContextSubgraphState


def _route_after_rag(state: ContextSubgraphState) -> str:
    """Route after RAG scoring: need web supplement or proceed."""
    if state.get("needs_web_supplement", False):
        return "retrieve_web_context"
    return "score_combined_context"


def build_context_subgraph() -> StateGraph:
    """Build the Context Subgraph."""
    graph = StateGraph(ContextSubgraphState)

    graph.add_node("route_sources", route_sources)
    graph.add_node("extract_user_context_requirements", extract_user_context_requirements)
    graph.add_node("retrieve_rag_context", retrieve_rag_context)
    graph.add_node("score_rag_context", score_rag_context)
    graph.add_node("retrieve_web_context", retrieve_web_context)
    graph.add_node("score_combined_context", score_combined_context)
    graph.add_node("save_evidence_map", save_evidence_map)

    graph.set_entry_point("route_sources")
    graph.add_edge("route_sources", "extract_user_context_requirements")
    graph.add_edge("extract_user_context_requirements", "retrieve_rag_context")
    graph.add_edge("retrieve_rag_context", "score_rag_context")
    graph.add_conditional_edges(
        "score_rag_context",
        _route_after_rag,
        {
            "retrieve_web_context": "retrieve_web_context",
            "score_combined_context": "score_combined_context",
        },
    )
    graph.add_edge("retrieve_web_context", "score_combined_context")
    graph.add_edge("score_combined_context", "save_evidence_map")
    graph.add_edge("save_evidence_map", END)
    return graph
