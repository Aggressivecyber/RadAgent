"""Gate validation subgraph builder."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_core.gates.base_gates import run_base_gates
from agent_core.gates.credibility_gate import run_credibility_gate
from agent_core.gates.g4_modeling_gates import run_g4_modeling_gates
from agent_core.gates.gate_runner import finalize_gate_results, load_gate_inputs
from agent_core.gates.schemas import GateSubgraphState


def build_gate_validation_subgraph() -> StateGraph:
    """Build the Gate Validation Subgraph."""
    graph = StateGraph(GateSubgraphState)

    graph.add_node("load_gate_inputs", load_gate_inputs)
    graph.add_node("run_base_gates", run_base_gates)
    graph.add_node("run_g4_modeling_gates", run_g4_modeling_gates)
    graph.add_node("run_credibility_gate", run_credibility_gate)
    graph.add_node("finalize_gate_results", finalize_gate_results)

    graph.set_entry_point("load_gate_inputs")
    graph.add_edge("load_gate_inputs", "run_base_gates")
    graph.add_edge("run_base_gates", "run_g4_modeling_gates")
    graph.add_edge("run_g4_modeling_gates", "run_credibility_gate")
    graph.add_edge("run_credibility_gate", "finalize_gate_results")
    graph.add_edge("finalize_gate_results", END)
    return graph
