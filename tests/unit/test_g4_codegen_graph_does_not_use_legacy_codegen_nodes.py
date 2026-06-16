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


def test_graph_uses_full_project_agent_node():
    """g4_codegen_graph must use the full-project agentic node by default."""
    graph_file = Path("agent_core/graph/subgraphs/g4_codegen_graph.py")
    source = graph_file.read_text()

    # Must keep planning/audit nodes from graph_nodes and code through the
    # full-project writer.
    assert "from agent_core.g4_codegen.graph_nodes import" in source
    assert "geant4_project_agent_node" in source
    assert "run_module_layer_node" not in source
    assert "integration_assembler_node" not in source
    assert "global_integration_agent_node" not in source
    assert "runtime_execution_audit_node" in source
    assert "run_module_hard_gate_node" not in source
    assert "run_module_llm_gate_node" not in source
