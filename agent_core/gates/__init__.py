"""Gate Validation Subgraph — runs all quality gates."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import finalize_gate_results, load_gate_inputs, run_base_gates, run_g4_modeling_gates
from .schemas import GateSubgraphState


def build_gate_validation_subgraph() -> StateGraph:
    """Build the Gate Validation Subgraph.

    Flow:
        load_gate_inputs → run_base_gates (0-11) → run_g4_modeling_gates (A-G)
        → finalize_gate_results
    """
    graph = StateGraph(GateSubgraphState)

    graph.add_node("load_gate_inputs", load_gate_inputs)
    graph.add_node("run_base_gates", run_base_gates)
    graph.add_node("run_g4_modeling_gates", run_g4_modeling_gates)
    graph.add_node("finalize_gate_results", finalize_gate_results)

    graph.set_entry_point("load_gate_inputs")
    graph.add_edge("load_gate_inputs", "run_base_gates")
    graph.add_edge("run_base_gates", "run_g4_modeling_gates")
    graph.add_edge("run_g4_modeling_gates", "finalize_gate_results")
    graph.add_edge("finalize_gate_results", END)

    return graph
