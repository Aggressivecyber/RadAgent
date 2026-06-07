"""Tests for subgraph compilation and structure."""

from __future__ import annotations


def test_context_subgraph_compiles() -> None:
    """Context subgraph should compile without errors."""
    from agent_core.context import build_context_subgraph

    graph = build_context_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_task_planning_subgraph_compiles() -> None:
    """Task planning subgraph should compile without errors."""
    from agent_core.planning import build_task_planning_subgraph

    graph = build_task_planning_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_g4_modeling_subgraph_compiles() -> None:
    """G4 modeling subgraph should compile without errors."""
    from agent_core.graph.subgraphs.g4_modeling_graph import build_g4_modeling_subgraph

    graph = build_g4_modeling_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_g4_codegen_subgraph_compiles() -> None:
    """G4 codegen subgraph should compile without errors."""
    from agent_core.graph.subgraphs.g4_codegen_graph import build_g4_codegen_subgraph

    graph = build_g4_codegen_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_patch_subgraph_compiles() -> None:
    """Patch subgraph should compile without errors."""
    from agent_core.patching import build_patch_subgraph

    graph = build_patch_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_gate_subgraph_compiles() -> None:
    """Gate subgraph should compile without errors."""
    from agent_core.gates import build_gate_validation_subgraph

    graph = build_gate_validation_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_artifact_subgraph_compiles() -> None:
    """Artifact subgraph should compile without errors."""
    from agent_core.artifacts import build_artifact_subgraph

    graph = build_artifact_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_report_subgraph_compiles() -> None:
    """Report subgraph should compile without errors."""
    from agent_core.reports import build_report_subgraph

    graph = build_report_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_main_graph_compiles() -> None:
    """Main graph should compile without errors."""
    from agent_core.graph.main_graph import compile_main_graph

    graph = compile_main_graph()
    assert graph is not None


def test_main_state_has_path_fields() -> None:
    """Main state should have path-based fields, not inline data."""
    from agent_core.graph.main_state import RadAgentMainState

    annotations = RadAgentMainState.__annotations__
    # Must have path fields
    path_fields = [
        "context_report_path",
        "evidence_map_path",
        "task_spec_path",
        "g4_model_ir_path",
        "component_specs_dir",
        "construction_ledger_path",
        "code_module_plan_path",
        "proposed_patch_path",
        "generated_code_dir",
        "gate_results_path",
        "review_artifact_dir",
        "final_report_path",
    ]
    for field in path_fields:
        assert field in annotations, f"Missing path field: {field}"

    # Must NOT have inline data fields
    forbidden = [
        "g4_model_ir",  # should be path, not dict
        "simulation_ir",  # old field
        "rag_context",  # should be in file
        "g4_context",  # old naming
        "tcad_context",  # removed
        "spice_context",  # removed
    ]
    for field in forbidden:
        assert field not in annotations, f"Forbidden inline field present: {field}"
