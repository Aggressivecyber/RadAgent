"""Report subgraph builder."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_core.reports.nodes import generate_final_report
from agent_core.reports.schemas import ReportSubgraphState


def build_report_subgraph() -> StateGraph:
    """Build the Report Subgraph."""
    graph = StateGraph(ReportSubgraphState)

    graph.add_node("generate_final_report", generate_final_report)
    graph.set_entry_point("generate_final_report")
    graph.add_edge("generate_final_report", END)
    return graph
