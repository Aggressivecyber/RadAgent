"""G4 Codegen Subgraph — module agent pipeline for Geant4 code generation.

Flow:
    load_model_ir
    → build_codegen_plan
    → plan_geometry_strategy
    → plan_code_architecture
    → build_module_contracts
    → build_module_contexts
    → [for each module: agent → hard_gate → llm_gate → repair_if_needed]
    → build_interface_contracts
    → integration_assembler
    → static_semantic_scanner
    → cross_file_hard_gate
    → cross_file_llm_gate
    → persist_codegen_output
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from agent_core.g4_codegen import load_model_ir
from agent_core.g4_codegen.graph_nodes import (
    build_codegen_plan_node,
    build_interface_contracts_node,
    build_module_contexts_node,
    build_module_contracts_node,
    cross_file_hard_gate_node,
    cross_file_llm_gate_node,
    integration_assembler_node,
    persist_codegen_output_node,
    plan_code_architecture_node,
    plan_geometry_strategy_node,
    repair_module_node,
    run_module_agent_node,
    run_module_hard_gate_node,
    run_module_llm_gate_node,
    static_semantic_scanner_node,
)
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState

# Module execution order
MODULE_ORDER = [
    "material",
    "geometry",
    "placement",
    "source",
    "physics",
    "sensitive_detector",
    "scoring",
    "output_manager",
    "action_initialization",
    "main_cmake",
]


def build_g4_codegen_subgraph() -> StateGraph:
    """Build the G4 Codegen Subgraph with module agent pipeline."""
    graph = StateGraph(G4CodegenSubgraphState)

    # ── I/O nodes ─────────────────────────────────────────────────────
    graph.add_node("load_model_ir", load_model_ir)

    # ── Planning nodes ────────────────────────────────────────────────
    graph.add_node("build_codegen_plan", build_codegen_plan_node)
    graph.add_node("plan_geometry_strategy", plan_geometry_strategy_node)
    graph.add_node("plan_code_architecture", plan_code_architecture_node)
    graph.add_node("build_module_contracts", build_module_contracts_node)
    graph.add_node("build_module_contexts", build_module_contexts_node)

    # ── Module agent nodes (one per module) ───────────────────────────
    for module_name in MODULE_ORDER:
        # Agent node
        graph.add_node(
            f"run_{module_name}_agent",
            _make_module_agent_node(module_name),
        )
        # Hard gate node
        graph.add_node(
            f"{module_name}_hard_gate",
            _make_hard_gate_node(module_name),
        )
        # LLM gate node
        graph.add_node(
            f"{module_name}_llm_gate",
            _make_llm_gate_node(module_name),
        )
        # Repair node
        graph.add_node(
            f"repair_{module_name}",
            _make_repair_node(module_name),
        )

    # ── Integration nodes ─────────────────────────────────────────────
    graph.add_node("build_interface_contracts", build_interface_contracts_node)
    graph.add_node("integration_assembler", integration_assembler_node)
    graph.add_node("static_semantic_scanner", static_semantic_scanner_node)
    graph.add_node("cross_file_hard_gate", cross_file_hard_gate_node)
    graph.add_node("cross_file_llm_gate", cross_file_llm_gate_node)
    graph.add_node("persist_codegen_output", persist_codegen_output_node)

    # ── Flow: Planning ────────────────────────────────────────────────
    graph.set_entry_point("load_model_ir")
    graph.add_edge("load_model_ir", "build_codegen_plan")
    graph.add_edge("build_codegen_plan", "plan_geometry_strategy")
    graph.add_edge("plan_geometry_strategy", "plan_code_architecture")
    graph.add_edge("plan_code_architecture", "build_module_contracts")
    graph.add_edge("build_module_contracts", "build_module_contexts")

    # ── Flow: Module agents (sequential) ──────────────────────────────
    # First module connects from build_module_contexts
    graph.add_edge("build_module_contexts", f"run_{MODULE_ORDER[0]}_agent")

    for i, module_name in enumerate(MODULE_ORDER):
        # Agent → Hard gate
        graph.add_edge(f"run_{module_name}_agent", f"{module_name}_hard_gate")

        # Hard gate → conditional: LLM gate or repair or next module
        graph.add_conditional_edges(
            f"{module_name}_hard_gate",
            _route_after_hard_gate(module_name),
            {
                f"{module_name}_llm_gate": f"{module_name}_llm_gate",
                f"repair_{module_name}": f"repair_{module_name}",
                _next_module_or_integration(i): _next_module_or_integration(i),
            },
        )

        # LLM gate → conditional: next module or repair
        graph.add_conditional_edges(
            f"{module_name}_llm_gate",
            _route_after_llm_gate(module_name),
            {
                _next_module_or_integration(i): _next_module_or_integration(i),
                f"repair_{module_name}": f"repair_{module_name}",
            },
        )

        # Repair → conditional: hard gate or skip to next module
        graph.add_conditional_edges(
            f"repair_{module_name}",
            _route_after_repair(module_name),
            {
                f"{module_name}_hard_gate": f"{module_name}_hard_gate",
                _next_module_or_integration(i): _next_module_or_integration(i),
            },
        )

    # ── Flow: Integration ─────────────────────────────────────────────
    graph.add_edge("build_interface_contracts", "integration_assembler")
    graph.add_edge("integration_assembler", "static_semantic_scanner")
    graph.add_conditional_edges(
        "static_semantic_scanner",
        _route_after_static_scan,
        {
            "cross_file_hard_gate": "cross_file_hard_gate",
            "persist_codegen_output": "persist_codegen_output",
        },
    )
    graph.add_conditional_edges(
        "cross_file_hard_gate",
        _route_after_cross_hard_gate,
        {
            "cross_file_llm_gate": "cross_file_llm_gate",
            "persist_codegen_output": "persist_codegen_output",
        },
    )
    graph.add_conditional_edges(
        "cross_file_llm_gate",
        _route_after_cross_llm_gate,
        {
            "persist_codegen_output": "persist_codegen_output",
        },
    )
    graph.add_edge("persist_codegen_output", END)

    return graph


# ── Node factories ───────────────────────────────────────────────────


def _make_module_agent_node(module_name: str) -> Any:
    """Create a module agent node function."""
    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await run_module_agent_node(state, module_name)
    return _run


def _make_hard_gate_node(module_name: str) -> Any:
    """Create a hard gate node function."""
    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await run_module_hard_gate_node(state, module_name)
    return _run


def _make_llm_gate_node(module_name: str) -> Any:
    """Create an LLM gate node function."""
    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await run_module_llm_gate_node(state, module_name)
    return _run


def _make_repair_node(module_name: str) -> Any:
    """Create a repair node function."""
    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await repair_module_node(state, module_name)
    return _run


# ── Routing functions ────────────────────────────────────────────────


def _next_module_or_integration(current_index: int) -> str:
    """Get the next module name or integration node."""
    if current_index + 1 < len(MODULE_ORDER):
        return f"run_{MODULE_ORDER[current_index + 1]}_agent"
    return "build_interface_contracts"


def _route_after_hard_gate(module_name: str) -> Any:
    """Route after hard gate: pass → LLM gate, fail → repair."""
    def _route(state: G4CodegenSubgraphState) -> str:
        gate_results = state.get("module_gate_results", {})
        hard_gate = gate_results.get(module_name, {}).get("hard", {})
        if hard_gate.get("status") == "pass":
            return f"{module_name}_llm_gate"
        return f"repair_{module_name}"
    return _route


def _route_after_llm_gate(module_name: str) -> Any:
    """Route after LLM gate: pass → next, fail → repair."""
    def _route(state: G4CodegenSubgraphState) -> str:
        gate_results = state.get("module_gate_results", {})
        llm_gate = gate_results.get(module_name, {}).get("llm", {})
        if llm_gate.get("status") == "pass":
            idx = MODULE_ORDER.index(module_name)
            return _next_module_or_integration(idx)
        return f"repair_{module_name}"
    return _route


def _route_after_cross_hard_gate(state: G4CodegenSubgraphState) -> str:
    """Route after cross-file hard gate."""
    gate = state.get("cross_file_hard_gate", {})
    if gate.get("status") == "pass":
        return "cross_file_llm_gate"
    return "persist_codegen_output"


def _route_after_cross_llm_gate(state: G4CodegenSubgraphState) -> str:
    """Route after cross-file LLM gate."""
    return "persist_codegen_output"


def _route_after_static_scan(state: G4CodegenSubgraphState) -> str:
    """Route after static semantic scan: pass → cross_file_hard_gate, fail → persist."""
    scan = state.get("static_semantic_scan", {})
    if scan.get("status") == "pass":
        return "cross_file_hard_gate"
    return "persist_codegen_output"


def _route_after_repair(module_name: str) -> Any:
    """Route after repair: success → hard gate, failed → persist (terminate codegen).

    P0-14/P0-15: When repair fails after max attempts, terminate codegen
    by routing to persist_codegen_output. Do NOT loop back to hard gate.
    """
    def _route(state: G4CodegenSubgraphState) -> str:
        repair_results = state.get("module_repair_results", {})
        repair = repair_results.get(module_name, {})
        if repair.get("status") == "failed":
            # P0-15: Repair failed — terminate codegen, go to persist
            return "persist_codegen_output"
        return f"{module_name}_hard_gate"
    return _route
