"""Main orchestration graph for RadAgent.

The main graph is EXTREMELY SIMPLE — it only schedules subgraphs.
It never processes geometry details, C++ code, Gate specifics, or
artifact content directly. All domain logic lives in subgraphs.

Flow:
    prepare_workspace
      → context_subgraph
      → task_planning_subgraph
      → g4_modeling_subgraph
      → g4_codegen_subgraph
      → patch_subgraph
      → gate_subgraph
      → artifact_subgraph
      → report_subgraph
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from agent_core.config.workspace import ensure_job_dirs
from agent_core.graph.main_routes import (
    route_after_artifact,
    route_after_context,
    route_after_g4_codegen,
    route_after_g4_modeling,
    route_after_gates,
    route_after_human_confirmation,
    route_after_patch,
    route_after_task_planning,
)
from agent_core.graph.main_state import RadAgentMainState

# ─── Workspace preparation node ──────────────────────────────────────


async def prepare_workspace(state: RadAgentMainState) -> dict[str, Any]:
    """Create job directory structure and initialize state.

    Generates a job_id with a human-readable title suffix via dsv4lite
    when no explicit job_id is provided by the user.
    """
    from agent_core.naming import build_job_id

    job_id = await build_job_id(
        state.get("job_id", ""),
        state.get("user_query", ""),
    )

    job_dir = ensure_job_dirs(job_id)
    request_dir = job_dir / "00_request"
    request_dir.mkdir(parents=True, exist_ok=True)
    (request_dir / "user_query.md").write_text(
        f"# User Query\n\n{state.get('user_query', '')}\n"
    )

    return {
        "job_id": job_id,
        "retry_count": 0,
        "max_retries_reached": False,
        "errors": [],
        "current_node": "prepare_workspace",
    }


# ─── Subgraph placeholder creators ───────────────────────────────────
# Each subgraph is compiled independently and wrapped as a main-graph node.
# The wrapper reads paths from main state, invokes the subgraph, and
# writes subgraph output paths back to main state.


def _make_context_subgraph_node() -> Any:
    """Create the context subgraph node."""
    from agent_core.graph.subgraphs.context_graph import build_context_subgraph

    subgraph = build_context_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "user_query": state.get("user_query", ""),
            "required_sources": ["geant4"],
        })
        return {
            "context_decision": result.get("context_decision", "block_no_context"),
            "context_report_path": result.get("context_report_path", ""),
            "evidence_map_path": result.get("evidence_map_path", ""),
            "current_node": "context_subgraph",
        }

    return _run


def _make_task_planning_subgraph_node() -> Any:
    """Create the task planning subgraph node."""
    from agent_core.graph.subgraphs.task_planning_graph import (
        build_task_planning_subgraph,
    )

    subgraph = build_task_planning_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "user_query": state.get("user_query", ""),
            "context_report_path": state.get("context_report_path", ""),
            "evidence_map_path": state.get("evidence_map_path", ""),
        })
        return {
            "task_spec_path": result.get("task_spec_path", ""),
            "simulation_scope": result.get("simulation_scope", ["geant4"]),
            "task_planning_status": result.get("task_planning_status", "failed"),
            "current_node": "task_planning_subgraph",
        }

    return _run


def _make_g4_modeling_subgraph_node() -> Any:
    """Create the G4 modeling subgraph node."""
    from agent_core.graph.subgraphs.g4_modeling_graph import build_g4_modeling_subgraph

    subgraph = build_g4_modeling_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "user_query": state.get("user_query", ""),
            "task_spec_path": state.get("task_spec_path", ""),
            "evidence_map_path": state.get("evidence_map_path", ""),
        })
        return {
            "g4_model_ir_path": result.get("g4_model_ir_path", ""),
            "component_specs_dir": result.get("component_specs_dir", ""),
            "interfaces_path": result.get("interfaces_path", ""),
            "construction_ledger_path": result.get("construction_ledger_path", ""),
            "model_review_report_path": result.get("model_review_report_path", ""),
            "g4_modeling_status": result.get("g4_modeling_status", "failed"),
            "current_node": "g4_modeling_subgraph",
        }

    return _run


def _make_human_confirmation_subgraph_node() -> Any:
    """Create the human confirmation subgraph node."""
    from agent_core.graph.subgraphs.human_confirmation_graph import (
        build_human_confirmation_subgraph,
    )

    subgraph = build_human_confirmation_subgraph()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "user_query": state.get("user_query", ""),
            "g4_model_ir_path": state.get("g4_model_ir_path", ""),
            "evidence_map_path": state.get("evidence_map_path", ""),
            "human_confirmation_round": state.get("human_confirmation_round", 1),
            "raw_human_response": state.get("raw_human_response", {}),
            "confirmation_request_path": state.get("confirmation_request_path", ""),
            "confirmation_response_path": state.get("confirmation_response_path", ""),
            "confirmation_record_path": state.get("confirmation_record_path", ""),
            "confirmed_model_plan_path": state.get("confirmed_model_plan_path", ""),
        })
        return {
            "confirmation_status": result.get("confirmation_status", "failed"),
            "confirmation_request_path": result.get("confirmation_request_path", ""),
            "confirmation_response_path": result.get("confirmation_response_path", ""),
            "confirmation_record_path": result.get("confirmation_record_path", ""),
            "confirmed_model_plan_path": result.get("confirmed_model_plan_path", ""),
            "unconfirmed_assumptions_count": result.get("unconfirmed_count", 0),
            "human_confirmation_required": result.get("requires_human_confirmation", False),
            "human_confirmation_round": state.get("human_confirmation_round", 1) + (
                1 if result.get("confirmation_status") == "pending" else 0
            ),
            "confirmation_report_path": result.get("confirmation_report_path", ""),
            "human_confirmation_edited_fields": result.get("edited_fields", []),
            "current_node": "human_confirmation_subgraph",
        }

    return _run


def _make_g4_codegen_subgraph_node() -> Any:
    """Create the G4 codegen subgraph node."""
    from agent_core.graph.subgraphs.g4_codegen_graph import build_g4_codegen_subgraph

    subgraph = build_g4_codegen_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "g4_model_ir_path": state.get("g4_model_ir_path", ""),
            "component_specs_dir": state.get("component_specs_dir", ""),
            "construction_ledger_path": state.get("construction_ledger_path", ""),
        })
        return {
            "code_module_plan_path": result.get("code_module_plan_path", ""),
            "proposed_patch_path": result.get("proposed_patch_path", ""),
            "generated_code_dir": result.get("generated_code_dir", ""),
            "g4_codegen_status": result.get("g4_codegen_status", "failed"),
            "current_node": "g4_codegen_subgraph",
        }

    return _run


def _make_patch_subgraph_node() -> Any:
    """Create the patch subgraph node."""
    from agent_core.graph.subgraphs.patch_graph import build_patch_subgraph

    subgraph = build_patch_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "proposed_patch_path": state.get("proposed_patch_path", ""),
            "generated_code_dir": state.get("generated_code_dir", ""),
        })
        return {
            "patch_review_path": result.get("patch_review_path", ""),
            "applied_patch_path": result.get("applied_patch_path", ""),
            "patch_applied_at": result.get("patch_applied_at", ""),
            "patch_status": result.get("patch_status", "failed"),
            "current_node": "patch_subgraph",
        }

    return _run


def _make_gate_subgraph_node() -> Any:
    """Create the gate validation subgraph node."""
    from agent_core.graph.subgraphs.gate_validation_graph import (
        build_gate_validation_subgraph,
    )

    subgraph = build_gate_validation_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "execution_mode": state.get("execution_mode", "dev_no_geant4_env"),
            "g4_model_ir_path": state.get("g4_model_ir_path", ""),
            "generated_code_dir": state.get("generated_code_dir", ""),
            "applied_patch_path": state.get("applied_patch_path", ""),
            "patch_applied_at": state.get("patch_applied_at", ""),
            "task_spec_path": state.get("task_spec_path", ""),
            "context_decision": state.get("context_decision", ""),
            "retry_count": state.get("retry_count", 0),
        })
        new_retry = state.get("retry_count", 0) + (
            1 if result.get("validation_status") == "FAILED" else 0
        )
        return {
            "gate_results_path": result.get("gate_results_path", ""),
            "validation_status": result.get("validation_status", "FAILED"),
            "failed_gates": result.get("failed_gates", []),
            "skipped_gates": result.get("skipped_gates", []),
            "retry_count": new_retry,
            "max_retries_reached": new_retry >= 5,
            "current_node": "gate_subgraph",
        }

    return _run


def _make_artifact_subgraph_node() -> Any:
    """Create the artifact collection subgraph node."""
    from agent_core.graph.subgraphs.artifact_graph import build_artifact_subgraph

    subgraph = build_artifact_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "gate_results_path": state.get("gate_results_path", ""),
            "g4_model_ir_path": state.get("g4_model_ir_path", ""),
            "model_review_report_path": state.get("model_review_report_path", ""),
            "construction_ledger_path": state.get("construction_ledger_path", ""),
            "code_module_plan_path": state.get("code_module_plan_path", ""),
            "proposed_patch_path": state.get("proposed_patch_path", ""),
            "validation_status": state.get("validation_status", ""),
        })
        return {
            "review_artifact_dir": result.get("review_artifact_dir", ""),
            "artifact_manifest_path": result.get("artifact_manifest_path", ""),
            "artifact_status": result.get("artifact_status", "failed"),
            "current_node": "artifact_subgraph",
        }

    return _run


def _make_report_subgraph_node() -> Any:
    """Create the report generation subgraph node."""
    from agent_core.graph.subgraphs.report_graph import build_report_subgraph

    subgraph = build_report_subgraph().compile()

    async def _run(state: RadAgentMainState) -> dict[str, Any]:
        result = await subgraph.ainvoke({
            "job_id": state.get("job_id", ""),
            "user_query": state.get("user_query", ""),
            "execution_mode": state.get("execution_mode", "dev_no_geant4_env"),
            "context_decision": state.get("context_decision", ""),
            "validation_status": state.get("validation_status", ""),
            "g4_model_ir_path": state.get("g4_model_ir_path", ""),
            "gate_results_path": state.get("gate_results_path", ""),
            "model_review_report_path": state.get("model_review_report_path", ""),
            "simulation_scope": state.get("simulation_scope", []),
            "failed_gates": state.get("failed_gates", []),
            "errors": state.get("errors", []),
        })
        return {
            "final_report_path": result.get("final_report_path", ""),
            "verified": result.get("verified", False),
            "termination_reason": result.get("termination_reason", ""),
            "current_node": "report_subgraph",
        }

    return _run


# ─── Main graph builder ──────────────────────────────────────────────


def build_main_graph() -> StateGraph:
    """Build the main orchestration graph.

    The main graph is a simple linear sequence with conditional routing.
    Each node is a subgraph wrapper that handles domain logic internally.
    """
    graph = StateGraph(RadAgentMainState)

    # Add workspace preparation (not a subgraph — just directory setup)
    graph.add_node("prepare_workspace", prepare_workspace)

    # Add subgraph wrapper nodes
    graph.add_node("context_subgraph", _make_context_subgraph_node())
    graph.add_node("task_planning_subgraph", _make_task_planning_subgraph_node())
    graph.add_node("g4_modeling_subgraph", _make_g4_modeling_subgraph_node())
    graph.add_node("human_confirmation_subgraph", _make_human_confirmation_subgraph_node())
    graph.add_node("g4_codegen_subgraph", _make_g4_codegen_subgraph_node())
    graph.add_node("patch_subgraph", _make_patch_subgraph_node())
    graph.add_node("gate_subgraph", _make_gate_subgraph_node())
    graph.add_node("artifact_subgraph", _make_artifact_subgraph_node())
    graph.add_node("report_subgraph", _make_report_subgraph_node())

    # Set entry point
    graph.set_entry_point("prepare_workspace")

    # Linear edges: workspace → context
    graph.add_edge("prepare_workspace", "context_subgraph")

    # Conditional: context → task_planning or report
    graph.add_conditional_edges(
        "context_subgraph",
        route_after_context,
        {
            "task_planning_subgraph": "task_planning_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: task_planning → g4_modeling or report
    graph.add_conditional_edges(
        "task_planning_subgraph",
        route_after_task_planning,
        {
            "g4_modeling_subgraph": "g4_modeling_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: g4_modeling → human_confirmation or g4_codegen or report
    graph.add_conditional_edges(
        "g4_modeling_subgraph",
        route_after_g4_modeling,
        {
            "human_confirmation_subgraph": "human_confirmation_subgraph",
            "g4_codegen_subgraph": "g4_codegen_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: human_confirmation → g4_codegen, context, or report
    graph.add_conditional_edges(
        "human_confirmation_subgraph",
        route_after_human_confirmation,
        {
            "g4_codegen_subgraph": "g4_codegen_subgraph",
            "context_subgraph": "context_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: g4_codegen → patch or report
    graph.add_conditional_edges(
        "g4_codegen_subgraph",
        route_after_g4_codegen,
        {
            "patch_subgraph": "patch_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: patch → gates or report
    graph.add_conditional_edges(
        "patch_subgraph",
        route_after_patch,
        {
            "gate_subgraph": "gate_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Conditional: gates → artifact (success) or retry subgraph or report
    graph.add_conditional_edges(
        "gate_subgraph",
        route_after_gates,
        {
            "artifact_subgraph": "artifact_subgraph",
            "context_subgraph": "context_subgraph",
            "task_planning_subgraph": "task_planning_subgraph",
            "g4_modeling_subgraph": "g4_modeling_subgraph",
            "g4_codegen_subgraph": "g4_codegen_subgraph",
            "patch_subgraph": "patch_subgraph",
            "report_subgraph": "report_subgraph",
        },
    )

    # Artifact → report (always)
    graph.add_conditional_edges(
        "artifact_subgraph",
        route_after_artifact,
        {
            "report_subgraph": "report_subgraph",
        },
    )

    # Report → END (always)
    graph.add_edge("report_subgraph", END)

    return graph


def compile_main_graph() -> Any:
    """Build and compile the main graph, ready for execution."""
    return build_main_graph().compile()
