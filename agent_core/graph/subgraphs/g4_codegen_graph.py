"""G4 Codegen Subgraph — module agent pipeline for Geant4 code generation.

Flow:
    load_model_ir
    → build_codegen_plan
    → plan_geometry_strategy
    → plan_code_architecture
    → build_module_contracts
    → build_module_contexts
    → build_interface_contracts
    → geant4_project_agent
    → runtime_execution_audit
    → physics_quality_review
    → persist_codegen_output

The Geant4 project agent is the default cross-project writer. It owns the
complete Geant4 workspace and uses build/smoke tool feedback before handing the
project to runtime/physics audit.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from agent_core.g4_codegen.graph_nodes import (
    build_codegen_plan_node,
    build_interface_contracts_node,
    build_module_contexts_node,
    build_module_contracts_node,
    continue_agentic_repair_node,
    persist_codegen_output_node,
    physics_quality_review_node,
    plan_code_architecture_node,
    plan_geometry_strategy_node,
    runtime_execution_audit_node,
)
from agent_core.g4_codegen.project_agent import geant4_project_agent_node
from agent_core.g4_codegen.io_nodes import load_model_ir
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState

AUDIT_REPAIR_ROUTE_LIMIT = 2


def build_g4_codegen_subgraph() -> StateGraph:
    """Build the G4 Codegen Subgraph with a full-project agentic pipeline."""
    graph = StateGraph(G4CodegenSubgraphState)

    # ── I/O nodes ─────────────────────────────────────────────────────
    graph.add_node("load_model_ir", load_model_ir)
    graph.add_node("continue_agentic_repair", continue_agentic_repair_node)

    # ── Planning nodes ────────────────────────────────────────────────
    graph.add_node("build_codegen_plan", build_codegen_plan_node)
    graph.add_node("plan_geometry_strategy", plan_geometry_strategy_node)
    graph.add_node("plan_code_architecture", plan_code_architecture_node)
    graph.add_node("build_module_contracts", build_module_contracts_node)
    graph.add_node("build_module_contexts", build_module_contexts_node)

    # ── Integration nodes ─────────────────────────────────────────────
    graph.add_node("build_interface_contracts", build_interface_contracts_node)
    graph.add_node("geant4_project_agent", geant4_project_agent_node)
    graph.add_node("runtime_execution_audit", runtime_execution_audit_node)
    graph.add_node("physics_quality_review", physics_quality_review_node)
    graph.add_node("persist_codegen_output", persist_codegen_output_node)

    # ── Flow: Planning ────────────────────────────────────────────────
    graph.set_entry_point("load_model_ir")
    graph.add_conditional_edges(
        "load_model_ir",
        _route_after_load_model_ir,
        {
            "build_codegen_plan": "build_codegen_plan",
            "continue_agentic_repair": "continue_agentic_repair",
        },
    )
    graph.add_conditional_edges(
        "continue_agentic_repair",
        _route_after_continue_agentic_repair,
        {
            "runtime_execution_audit": "runtime_execution_audit",
            "persist_codegen_output": "persist_codegen_output",
        },
    )
    graph.add_edge("build_codegen_plan", "plan_geometry_strategy")
    graph.add_edge("plan_geometry_strategy", "plan_code_architecture")
    graph.add_edge("plan_code_architecture", "build_module_contracts")
    graph.add_edge("build_module_contracts", "build_module_contexts")

    # ── Flow: Full-project agentic generation ────────────────────────
    graph.add_edge("build_module_contexts", "build_interface_contracts")

    # ── Flow: Integration ─────────────────────────────────────────────
    graph.add_edge("build_interface_contracts", "geant4_project_agent")
    graph.add_edge("geant4_project_agent", "runtime_execution_audit")
    graph.add_conditional_edges(
        "runtime_execution_audit",
        _route_after_runtime_execution_audit,
        {
            "physics_quality_review": "physics_quality_review",
            "geant4_project_agent": "geant4_project_agent",
            "persist_codegen_output": "persist_codegen_output",
        },
    )
    graph.add_conditional_edges(
        "physics_quality_review",
        _route_after_physics_quality_review,
        {
            "geant4_project_agent": "geant4_project_agent",
            "persist_codegen_output": "persist_codegen_output",
        },
    )
    graph.add_edge("persist_codegen_output", END)

    return graph


# ── Routing functions ────────────────────────────────────────────────


def _route_after_load_model_ir(state: G4CodegenSubgraphState) -> str:
    """Resume only the approved repair continuation path; otherwise start codegen."""
    try:
        turn_override = int(state.get("agentic_repair_max_turns_override") or 0)
    except (TypeError, ValueError):
        turn_override = 0
    if state.get("repair_continuation_status") == "approved" and turn_override > 0:
        return "continue_agentic_repair"
    return "build_codegen_plan"


def _route_after_continue_agentic_repair(state: G4CodegenSubgraphState) -> str:
    """Audit only successful continuation repairs; failed repairs surface to the UI."""
    report = state.get("global_integration_agent_report", {})
    if report.get("status") == "passed":
        return "runtime_execution_audit"
    return "persist_codegen_output"


def _route_after_layer_gate(layer_gate_name: str, next_node: str) -> Any:
    """Route after a layer gate.

    Legacy module layers are no longer the default codegen path. If this helper
    is used by older tests or compatibility code, failed layers fail closed
    instead of promoting partial module output into whole-project repair.
    """

    def _route(state: G4CodegenSubgraphState) -> str:
        gate = state.get("layer_gate_results", {}).get(layer_gate_name, {})
        if gate.get("status") == "pass":
            return next_node
        return "persist_codegen_output"

    return _route


def _has_repairable_module_files(state: G4CodegenSubgraphState) -> bool:
    """Compatibility helper for tests around the retired module-layer path."""
    module_results = state.get("module_results", {})
    if not isinstance(module_results, dict):
        return False
    for result in module_results.values():
        if not isinstance(result, dict):
            continue
        generated_files = result.get("generated_files")
        if isinstance(generated_files, list) and any(
            isinstance(item, dict)
            and item.get("path")
            and item.get("new_content") is not None
            for item in generated_files
        ):
            return True
    return False


def _route_after_runtime_execution_audit(state: G4CodegenSubgraphState) -> str:
    """Run physics review only after runtime authenticity passes.

    Failed runtime artifacts are repairable by the full-project agent because
    the previous patch is still concrete code, not a partial module fragment.
    """
    audit = state.get("runtime_execution_audit", {})
    if audit.get("status") == "pass":
        return "physics_quality_review"
    if _repair_attempts_remaining(state.get("runtime_audit_repair_attempts")):
        return "geant4_project_agent"
    return "persist_codegen_output"


def _route_after_physics_quality_review(state: G4CodegenSubgraphState) -> str:
    """Feed only code-repairable physics review failures back to the project agent."""
    review = state.get("physics_quality_review", {})
    status = str(review.get("status") or "")
    recommendation = str(review.get("routing_recommendation") or "").lower()
    if status == "pass" or recommendation == "accept":
        return "persist_codegen_output"
    if status == "needs_user_input" or recommendation == "request_user_input":
        return "persist_codegen_output"
    has_required_fixes = bool(review.get("required_fixes"))
    if (
        (recommendation == "repair_code" or has_required_fixes)
        and _repair_attempts_remaining(state.get("physics_review_repair_attempts"))
    ):
        return "geant4_project_agent"
    return "persist_codegen_output"


def _repair_attempts_remaining(value: Any) -> bool:
    try:
        attempts = int(value or 0)
    except (TypeError, ValueError):
        attempts = 0
    return attempts < AUDIT_REPAIR_ROUTE_LIMIT
