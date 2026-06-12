"""G4 Modeling Subgraph — converts user requirements into Geant4 Model IR.

This is the CORE subgraph. It transforms complex user requirements into a
structured Geant4 Model IR (g4_model_ir.json) through a pipeline of 15 nodes,
each responsible for exactly one modeling dimension.

Flow:
    load_task_spec
    → requirement_capture
    → evidence_retrieval
    → model_scope_guard (block if insufficient)
    → geometry_decomposition
    → coordinate_system
    → material_definition
    → source_definition
    → physics_list
    → sensitive_detector
    → scoring_design
    → model_ir_validation (persist failed IR on errors)
    → model_review_report
    → persist_model_ir
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agent_core.g4_modeling.nodes import (
    coordinate_system_node,
    evidence_retrieval_node,
    geometry_decomposition_node,
    material_definition_node,
    model_ir_validation_node,
    model_review_report_node,
    model_scope_guard_node,
    physics_list_node,
    requirement_capture_node,
    scoring_design_node,
    sensitive_detector_node,
    source_definition_node,
)
from agent_core.g4_modeling.subgraph_io import load_task_spec, persist_model_ir
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState


def _route_after_scope_guard(state: G4ModelingSubgraphState) -> str:
    """Block if evidence insufficient, else proceed."""
    guard_result = state.get("model_scope_guard_result", {})
    action = guard_result.get("action", "block") if isinstance(guard_result, dict) else "block"
    if action in ("proceed", "proceed_with_warnings"):
        return "geometry_decomposition_node"
    return "persist_model_ir"  # Will mark as failed


def _route_after_model_ir_validation(state: G4ModelingSubgraphState) -> str:
    """Route after model IR validation."""
    errors = state.get("model_ir_errors", [])
    if not errors:
        return "model_review_report_node"
    return "persist_model_ir"  # Will mark as failed


def build_g4_modeling_subgraph() -> StateGraph:
    """Build the G4 Modeling Subgraph."""
    graph = StateGraph(G4ModelingSubgraphState)

    # I/O adapter nodes
    graph.add_node("load_task_spec", load_task_spec)
    graph.add_node("persist_model_ir", persist_model_ir)

    # Core modeling nodes (15 total, reused from existing validated code)
    graph.add_node("requirement_capture_node", requirement_capture_node)
    graph.add_node("evidence_retrieval_node", evidence_retrieval_node)
    graph.add_node("model_scope_guard_node", model_scope_guard_node)
    graph.add_node("geometry_decomposition_node", geometry_decomposition_node)
    graph.add_node("coordinate_system_node", coordinate_system_node)
    graph.add_node("material_definition_node", material_definition_node)
    graph.add_node("source_definition_node", source_definition_node)
    graph.add_node("physics_list_node", physics_list_node)
    graph.add_node("sensitive_detector_node", sensitive_detector_node)
    graph.add_node("scoring_design_node", scoring_design_node)
    graph.add_node("model_ir_validation_node", model_ir_validation_node)
    graph.add_node("model_review_report_node", model_review_report_node)

    # Entry: load task spec
    graph.set_entry_point("load_task_spec")
    graph.add_edge("load_task_spec", "requirement_capture_node")

    # Requirement → evidence → scope guard
    graph.add_edge("requirement_capture_node", "evidence_retrieval_node")
    graph.add_edge("evidence_retrieval_node", "model_scope_guard_node")

    # Scope guard: proceed or terminate
    graph.add_conditional_edges(
        "model_scope_guard_node",
        _route_after_scope_guard,
        {
            "geometry_decomposition_node": "geometry_decomposition_node",
            "persist_model_ir": "persist_model_ir",
        },
    )

    # Geometry → coordinate → material → source → physics → SD → scoring
    graph.add_edge("geometry_decomposition_node", "coordinate_system_node")
    graph.add_edge("coordinate_system_node", "material_definition_node")
    graph.add_edge("material_definition_node", "source_definition_node")
    graph.add_edge("source_definition_node", "physics_list_node")
    graph.add_edge("physics_list_node", "sensitive_detector_node")
    graph.add_edge("sensitive_detector_node", "scoring_design_node")
    graph.add_edge("scoring_design_node", "model_ir_validation_node")

    # Validation: pass → review, fail → persist failed IR.
    # The modeling nodes are deterministic after the Lite draft; looping back
    # without new feedback only repeats the same validation failure.
    graph.add_conditional_edges(
        "model_ir_validation_node",
        _route_after_model_ir_validation,
        {
            "model_review_report_node": "model_review_report_node",
            "persist_model_ir": "persist_model_ir",
        },
    )

    # Review → persist
    graph.add_edge("model_review_report_node", "persist_model_ir")
    graph.add_edge("persist_model_ir", END)

    return graph
