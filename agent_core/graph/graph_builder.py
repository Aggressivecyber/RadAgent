"""LangGraph graph builder that assembles the full agent pipeline.

Uses a unified retrieve_required_context node instead of the old
fan-out (retrieve_g4/tcad/spice_context).  Only required sources
are queried; non-required sources return empty context and do not
affect the sufficiency score.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from agent_core.graph.routes import (
    route_after_classify_failure,
    route_after_combined_context,
    route_after_gate_checks,
    route_after_rag,
    route_after_sim_ir_validation,
    route_after_task_spec_validation,
)
from agent_core.graph.state import RadiationAgentState
from agent_core.nodes.apply_patch import apply_patch
from agent_core.nodes.build_simulation_ir import build_simulation_ir
from agent_core.nodes.build_task_spec import build_task_spec
from agent_core.nodes.classify_failure import classify_failure
from agent_core.nodes.generate_report import generate_report
from agent_core.nodes.generate_test_plan import generate_test_plan
from agent_core.nodes.parse_simulation_results import parse_simulation_results
from agent_core.nodes.parse_user_request import parse_user_request
from agent_core.nodes.plan_code_architecture import plan_code_architecture
from agent_core.nodes.plan_simulation import plan_simulation
from agent_core.nodes.prepare_local_rag_workspace import prepare_local_rag_workspace
from agent_core.nodes.retrieve_error_context import retrieve_error_context
from agent_core.nodes.retrieve_required_context import retrieve_required_context
from agent_core.nodes.retrieve_web_context import retrieve_web_context
from agent_core.nodes.review_code_patch import review_code_patch
from agent_core.nodes.route_rag import route_rag
from agent_core.nodes.run_gate_checks import run_gate_checks
from agent_core.nodes.score_combined_context_sufficiency import (
    score_combined_context_sufficiency,
)
from agent_core.nodes.score_rag_sufficiency import score_rag_sufficiency
from agent_core.nodes.validate_data_contract import validate_data_contract
from agent_core.nodes.validate_simulation_ir import validate_simulation_ir
from agent_core.nodes.validate_task_spec import validate_task_spec
from agent_core.nodes.write_code_patch import write_code_patch
from agent_core.nodes.write_fix_patch import write_fix_patch


def build_graph() -> StateGraph:
    """Build the complete RadAgent LangGraph pipeline."""
    graph = StateGraph(RadiationAgentState)

    # --- Add all nodes ---
    graph.add_node("prepare_local_rag_workspace", prepare_local_rag_workspace)
    graph.add_node("parse_user_request", parse_user_request)
    graph.add_node("build_task_spec", build_task_spec)
    graph.add_node("validate_task_spec", validate_task_spec)
    graph.add_node("build_simulation_ir", build_simulation_ir)
    graph.add_node("validate_simulation_ir", validate_simulation_ir)
    graph.add_node("route_rag", route_rag)
    graph.add_node("retrieve_required_context", retrieve_required_context)
    graph.add_node("score_rag_sufficiency", score_rag_sufficiency)
    graph.add_node("retrieve_web_context", retrieve_web_context)
    graph.add_node("score_combined_context_sufficiency", score_combined_context_sufficiency)
    graph.add_node("plan_simulation", plan_simulation)
    graph.add_node("plan_code_architecture", plan_code_architecture)
    graph.add_node("generate_test_plan", generate_test_plan)
    graph.add_node("write_code_patch", write_code_patch)
    graph.add_node("review_code_patch", review_code_patch)
    graph.add_node("apply_patch", apply_patch)
    graph.add_node("run_gate_checks", run_gate_checks)
    graph.add_node("classify_failure", classify_failure)
    graph.add_node("retrieve_error_context", retrieve_error_context)
    graph.add_node("write_fix_patch", write_fix_patch)
    graph.add_node("parse_simulation_results", parse_simulation_results)
    graph.add_node("validate_data_contract", validate_data_contract)
    graph.add_node("generate_report", generate_report)

    # --- Entry point ---
    graph.set_entry_point("prepare_local_rag_workspace")

    # --- Linear: workspace → parse request → task spec ---
    graph.add_edge("prepare_local_rag_workspace", "parse_user_request")
    graph.add_edge("parse_user_request", "build_task_spec")
    graph.add_edge("build_task_spec", "validate_task_spec")

    # Conditional: task spec valid? (3x fail → generate_report)
    graph.add_conditional_edges(
        "validate_task_spec",
        route_after_task_spec_validation,
        {
            "build_task_spec": "build_task_spec",
            "build_simulation_ir": "build_simulation_ir",
            "generate_report": "generate_report",
        },
    )

    graph.add_edge("build_simulation_ir", "validate_simulation_ir")

    # Conditional: sim IR valid? (3x fail → generate_report)
    graph.add_conditional_edges(
        "validate_simulation_ir",
        route_after_sim_ir_validation,
        {
            "build_simulation_ir": "build_simulation_ir",
            "route_rag": "route_rag",
            "generate_report": "generate_report",
        },
    )

    # Unified RAG retrieval (replaces old fan-out)
    # route_rag determines required/optional sources,
    # retrieve_required_context queries only what's needed
    graph.add_edge("route_rag", "retrieve_required_context")
    graph.add_edge("retrieve_required_context", "score_rag_sufficiency")

    # Conditional: RAG sufficient? (allow_rag / needs_web / block_no_context)
    graph.add_conditional_edges(
        "score_rag_sufficiency",
        route_after_rag,
        {
            "retrieve_web_context": "retrieve_web_context",
            "plan_simulation": "plan_simulation",
            "generate_report": "generate_report",
        },
    )

    # Web context -> combined scoring
    graph.add_edge("retrieve_web_context", "score_combined_context_sufficiency")

    # Conditional: combined context sufficient?
    graph.add_conditional_edges(
        "score_combined_context_sufficiency",
        route_after_combined_context,
        {
            "plan_simulation": "plan_simulation",
            "generate_report": "generate_report",
        },
    )

    # Planning pipeline
    graph.add_edge("plan_simulation", "plan_code_architecture")
    graph.add_edge("plan_code_architecture", "generate_test_plan")
    graph.add_edge("generate_test_plan", "write_code_patch")
    graph.add_edge("write_code_patch", "review_code_patch")
    graph.add_edge("review_code_patch", "apply_patch")
    graph.add_edge("apply_patch", "run_gate_checks")

    # Conditional: gates passed?
    graph.add_conditional_edges(
        "run_gate_checks",
        route_after_gate_checks,
        {
            "parse_simulation_results": "parse_simulation_results",
            "classify_failure": "classify_failure",
        },
    )

    # Failure handling loop
    graph.add_conditional_edges(
        "classify_failure",
        route_after_classify_failure,
        {
            "retrieve_error_context": "retrieve_error_context",
            "write_fix_patch": "write_fix_patch",
            "generate_report": "generate_report",
        },
    )
    graph.add_edge("retrieve_error_context", "write_fix_patch")
    graph.add_edge("write_fix_patch", "run_gate_checks")

    # Success path
    graph.add_edge("parse_simulation_results", "validate_data_contract")
    graph.add_edge("validate_data_contract", "generate_report")
    graph.add_edge("generate_report", END)

    return graph


def compile_graph() -> Any:
    """Build and compile the graph, ready for execution."""
    graph = build_graph()
    return graph.compile()
