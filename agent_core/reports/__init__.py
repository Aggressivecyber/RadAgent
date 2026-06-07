"""Report Subgraph — generate final report."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import generate_final_report
from .schemas import ReportSubgraphState


def build_report_subgraph() -> StateGraph:
    """Build the Report Subgraph (single node)."""
    graph = StateGraph(ReportSubgraphState)

    graph.add_node("generate_final_report", generate_final_report)
    graph.set_entry_point("generate_final_report")
    graph.add_edge("generate_final_report", END)

    return graph
