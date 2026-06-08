"""P0-12: g4_codegen_graph does not use legacy codegen nodes."""

from __future__ import annotations

import ast
from pathlib import Path


def test_graph_does_not_import_legacy_nodes():
    """g4_codegen_graph must not import old codegen nodes."""
    graph_file = Path("agent_core/graph/subgraphs/g4_codegen_graph.py")
    source = graph_file.read_text()
    tree = ast.parse(source)

    legacy_modules = [
        "g4_codegen.nodes.code_module_planner",
        "g4_codegen.nodes.component_builder_codegen",
        "g4_codegen.nodes.geometry_context_codegen",
        "g4_codegen.nodes.integration_assembler",
        "g4_modeling.codegen.material_registry_codegen",
        "g4_modeling.codegen.component_geometry_codegen",
        "g4_modeling.codegen.placement_codegen",
        "g4_modeling.codegen.source_codegen",
        "g4_modeling.codegen.physics_macro_codegen",
        "g4_modeling.codegen.sensitive_detector_codegen",
        "g4_modeling.codegen.scoring_codegen",
        "g4_modeling.codegen.output_manager_codegen",
    ]

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for legacy in legacy_modules:
                assert legacy not in node.module, (
                    f"g4_codegen_graph imports legacy module: {node.module}"
                )


def test_graph_uses_module_agent_nodes():
    """g4_codegen_graph must use module agent nodes."""
    graph_file = Path("agent_core/graph/subgraphs/g4_codegen_graph.py")
    source = graph_file.read_text()

    # Must import from graph_nodes (module agent system)
    assert "from agent_core.g4_codegen.graph_nodes import" in source
    # Must have module agent nodes
    assert "run_module_agent_node" in source
    assert "run_module_hard_gate_node" in source
    assert "run_module_llm_gate_node" in source
