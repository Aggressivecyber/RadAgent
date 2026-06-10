"""G4 Codegen Subgraph — module agent pipeline for Geant4 code generation.

Flow:
    load_model_ir
    → build_codegen_plan
    → plan_geometry_strategy
    → plan_code_architecture
    → build_module_contracts
    → build_module_contexts
    → [coarse module groups: simulation_core + beam_physics → runtime_app]
    → build_interface_contracts
    → integration_assembler
    → global_integration_agent
    → runtime_execution_audit
    → physics_quality_review
    → persist_codegen_output

The global integration agent is the only cross-module writer in the codegen
graph. It owns compile/runtime repair from real terminal observations.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from agent_core.g4_codegen.graph_nodes import (
    build_codegen_plan_node,
    build_interface_contracts_node,
    build_module_contexts_node,
    build_module_contracts_node,
    context_coordinator_node,
    global_integration_agent_node,
    integration_assembler_node,
    layer_consistency_gate_node,
    persist_codegen_output_node,
    physics_quality_review_node,
    plan_code_architecture_node,
    plan_geometry_strategy_node,
    run_module_layer_node,
    runtime_execution_audit_node,
)
from agent_core.g4_codegen.io_nodes import load_model_ir
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState

# Layered module execution plan. Modules inside a layer run in parallel; the
# layer gate waits for all module chains to complete before releasing the next
# layer.
MODULE_LAYERS = [
    (
        "core_modules",
        [
            "simulation_core",
            "beam_physics",
        ],
    ),
    (
        "runtime_modules",
        [
            "runtime_app",
        ],
    ),
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

    # ── Module layers ─────────────────────────────────────────────────
    for layer_index, (layer_name, module_names) in enumerate(MODULE_LAYERS):
        graph.add_node(
            f"run_{layer_name}",
            _make_module_layer_node(layer_name, module_names),
        )
        graph.add_node(
            f"{layer_name}_gate",
            _make_layer_gate_node(f"{layer_name}_gate", module_names),
        )
        graph.add_node(
            f"coordinate_{layer_name}_context",
            _make_context_coordinator_node(
                f"coordinate_{layer_name}_context",
                _target_modules_after_layer(layer_index),
            ),
        )

    # ── Integration nodes ─────────────────────────────────────────────
    graph.add_node("build_interface_contracts", build_interface_contracts_node)
    graph.add_node("integration_assembler", integration_assembler_node)
    graph.add_node("global_integration_agent", global_integration_agent_node)
    graph.add_node("runtime_execution_audit", runtime_execution_audit_node)
    graph.add_node("physics_quality_review", physics_quality_review_node)
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

        context_node = f"coordinate_{layer_name}_context"
        if layer_index + 1 < len(MODULE_LAYERS):
            next_node = f"run_{MODULE_LAYERS[layer_index + 1][0]}"
        else:
            next_node = "build_interface_contracts"
        graph.add_conditional_edges(
            gate_node,
            _route_after_layer_gate(gate_node, context_node),
            {
                context_node: context_node,
                "persist_codegen_output": "persist_codegen_output",
            },
        )
        graph.add_edge(context_node, next_node)

    # ── Flow: Integration ─────────────────────────────────────────────
    graph.add_edge("build_interface_contracts", "integration_assembler")
    graph.add_edge("integration_assembler", "global_integration_agent")
    graph.add_edge("global_integration_agent", "runtime_execution_audit")
    graph.add_conditional_edges(
        "runtime_execution_audit",
        _route_after_runtime_execution_audit,
        {
            "physics_quality_review": "physics_quality_review",
            "persist_codegen_output": "persist_codegen_output",
        },
    )
    graph.add_edge("physics_quality_review", "persist_codegen_output")
    graph.add_edge("persist_codegen_output", END)

    return graph


# ── Node factories ───────────────────────────────────────────────────


def _make_module_layer_node(layer_name: str, module_names: list[str]) -> Any:
    """Create a node that runs one module layer concurrently."""

    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await run_module_layer_node(state, layer_name, module_names)

    return _run


def _make_layer_gate_node(layer_gate_name: str, module_names: list[str]) -> Any:
    """Create a layer consistency gate node."""

    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await layer_consistency_gate_node(state, layer_gate_name, module_names)

    return _run


def _make_context_coordinator_node(coordinator_name: str, target_modules: list[str]) -> Any:
    """Create a context coordination graph node."""

    async def _run(state: G4CodegenSubgraphState) -> dict[str, Any]:
        return await context_coordinator_node(state, coordinator_name, target_modules)

    return _run


# ── Routing functions ────────────────────────────────────────────────


def _route_after_layer_gate(layer_gate_name: str, next_node: str) -> Any:
    """Route after a layer gate: pass continues, fail persists failed state."""

    def _route(state: G4CodegenSubgraphState) -> str:
        gate = state.get("layer_gate_results", {}).get(layer_gate_name, {})
        if gate.get("status") == "pass":
            return next_node
        return "persist_codegen_output"

    return _route


def _route_after_runtime_execution_audit(state: G4CodegenSubgraphState) -> str:
    """Run physics review only after runtime execution authenticity passes."""
    audit = state.get("runtime_execution_audit", {})
    if audit.get("status") == "pass":
        return "physics_quality_review"
    return "persist_codegen_output"


def _target_modules_after_layer(layer_index: int) -> list[str]:
    if layer_index + 1 < len(MODULE_LAYERS):
        return list(MODULE_LAYERS[layer_index + 1][1])
    return ["global_integration_agent", "runtime_execution_auditor", "physics_quality_reviewer"]
