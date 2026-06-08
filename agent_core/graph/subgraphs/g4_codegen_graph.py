"""G4 Codegen Subgraph — module agent pipeline for Geant4 code generation.

Flow:
    load_model_ir
    → build_codegen_plan
    → plan_geometry_strategy
    → plan_code_architecture
    → build_module_contracts
    → build_module_contexts
    → [layered parallel module groups: agent → hard_gate → llm_gate → repair_if_needed]
    → build_interface_contracts
    → integration_assembler
    → global_code_repair_agent
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
    global_code_repair_node,
    integration_assembler_node,
    layer_consistency_gate_node,
    persist_codegen_output_node,
    plan_code_architecture_node,
    plan_geometry_strategy_node,
    repair_module_node,
    run_module_agent_node,
    run_module_hard_gate_node,
    run_module_layer_node,
    run_module_llm_gate_node,
    static_semantic_scanner_node,
)
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState

# Layered module execution plan. Modules inside a layer run in parallel; the
# layer gate waits for all module chains to complete before releasing the next
# layer.
MODULE_LAYERS = [
    (
        "foundation_modules",
        [
            "material",
            "physics",
            "source",
            "output_manager",
        ],
    ),
    (
        "detector_modules",
        [
            "placement",
            "geometry",
            "sensitive_detector",
            "scoring",
        ],
    ),
    (
        "application_modules",
        [
            "action_initialization",
            "main_cmake",
        ],
    ),
]
MODULE_ORDER = [module for _, modules in MODULE_LAYERS for module in modules]


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
        graph.add_node(
            f"{module_name}_complete",
            _make_module_complete_node(module_name),
        )

    for layer_name, module_names in MODULE_LAYERS:
        graph.add_node(
            f"run_{layer_name}",
            _make_module_layer_node(layer_name, module_names),
        )
        graph.add_node(
            f"{layer_name}_gate",
            _make_layer_gate_node(f"{layer_name}_gate", module_names),
        )

    # ── Integration nodes ─────────────────────────────────────────────
    graph.add_node("build_interface_contracts", build_interface_contracts_node)
    graph.add_node("integration_assembler", integration_assembler_node)
    graph.add_node("global_code_repair_agent", global_code_repair_node)
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

    # ── Flow: Module agents (layered parallel DAG) ────────────────────
    graph.add_edge("build_module_contexts", f"run_{MODULE_LAYERS[0][0]}")

    for layer_index, (layer_name, module_names) in enumerate(MODULE_LAYERS):
        run_node = f"run_{layer_name}"
        gate_node = f"{layer_name}_gate"

        graph.add_edge(run_node, gate_node)

        if layer_index + 1 < len(MODULE_LAYERS):
            next_node = f"run_{MODULE_LAYERS[layer_index + 1][0]}"
        else:
            next_node = "build_interface_contracts"
        graph.add_conditional_edges(
            gate_node,
            _route_after_layer_gate(gate_node, next_node),
            {
                next_node: next_node,
                "persist_codegen_output": "persist_codegen_output",
            },
        )

    # ── Flow: Integration ─────────────────────────────────────────────
    graph.add_edge("build_interface_contracts", "integration_assembler")
    graph.add_edge("integration_assembler", "global_code_repair_agent")
    graph.add_edge("global_code_repair_agent", "static_semantic_scanner")
    graph.add_edge("static_semantic_scanner", "cross_file_hard_gate")
    graph.add_edge("cross_file_hard_gate", "cross_file_llm_gate")
    graph.add_edge("cross_file_llm_gate", "persist_codegen_output")
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


def _make_module_layer_node(layer_name: str, module_names: list[str]) -> Any:
    """Create a node that runs one module layer concurrently."""

    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await run_module_layer_node(state, layer_name, module_names)

    return _run


def _make_module_complete_node(module_name: str) -> Any:
    """Create a no-op terminal node for a module branch."""

    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return {"current_node": f"{module_name}_complete"}

    return _run


def _make_layer_start_node(layer_name: str) -> Any:
    """Create a no-op fan-out node for a parallel module layer."""

    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return {"current_node": f"start_{layer_name}"}

    return _run


def _make_layer_gate_node(layer_gate_name: str, module_names: list[str]) -> Any:
    """Create a layer consistency gate node."""

    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await layer_consistency_gate_node(state, layer_gate_name, module_names)

    return _run


# ── Routing functions ────────────────────────────────────────────────


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
    """Route after LLM gate: pass → module complete, fail → repair."""

    def _route(state: G4CodegenSubgraphState) -> str:
        gate_results = state.get("module_gate_results", {})
        llm_gate = gate_results.get(module_name, {}).get("llm", {})
        if llm_gate.get("status") == "pass":
            return f"{module_name}_complete"
        return f"repair_{module_name}"

    return _route


def _route_after_layer_gate(layer_gate_name: str, next_node: str) -> Any:
    """Route after a layer gate: pass continues, fail persists failed state."""

    def _route(state: G4CodegenSubgraphState) -> str:
        gate = state.get("layer_gate_results", {}).get(layer_gate_name, {})
        if gate.get("status") == "pass":
            return next_node
        return "persist_codegen_output"

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
    """Route after repair: success → hard gate, failed → module complete.

    The layer consistency gate terminates codegen if any branch failed. This
    avoids multiple parallel branches writing final output at once.
    """

    def _route(state: G4CodegenSubgraphState) -> str:
        repair_results = state.get("module_repair_results", {})
        repair = repair_results.get(module_name, {})
        if repair.get("status") == "failed":
            return f"{module_name}_complete"
        return f"{module_name}_hard_gate"

    return _route
