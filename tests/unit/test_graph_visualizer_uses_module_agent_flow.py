"""P0-13: graph_visualizer uses module agent flow, not legacy codegen."""

from __future__ import annotations

from agent_core.visualization.graph_visualizer import (
    draw_all,
    draw_combined,
    draw_main_graph,
    draw_subgraph,
    get_g4_codegen_subgraph_spec,
)


class TestGraphVisualizerUsesModuleAgentFlow:
    """Verify graph visualizer output includes module agent flow keywords."""

    def test_main_graph_contains_codegen_subgraph(self):
        diagram = draw_main_graph()
        assert "g4_codegen_subgraph" in diagram

    def test_codegen_spec_has_module_layers(self):
        spec = get_g4_codegen_subgraph_spec()
        node_ids = {n.node_id for n in spec.nodes}
        assert "run_core_modules" in node_ids
        assert "run_runtime_modules" in node_ids
        assert "coordinate_core_modules_context" in node_ids
        assert "coordinate_runtime_modules_context" in node_ids
        assert "run_simulation_core_agent" not in node_ids
        assert "run_beam_physics_agent" not in node_ids
        assert "run_runtime_app_agent" not in node_ids

    def test_codegen_spec_has_no_module_gates(self):
        spec = get_g4_codegen_subgraph_spec()
        node_ids = {n.node_id for n in spec.nodes}
        assert not any(node_id.endswith("_hard_gate") for node_id in node_ids)
        assert not any(node_id.endswith("_llm_gate") for node_id in node_ids)

    def test_codegen_spec_has_physics_review(self):
        spec = get_g4_codegen_subgraph_spec()
        node_ids = {n.node_id for n in spec.nodes}
        assert "global_integration_agent" in node_ids
        assert "runtime_execution_audit" in node_ids
        assert "physics_quality_review" in node_ids

    def test_codegen_spec_has_integration_assembler(self):
        spec = get_g4_codegen_subgraph_spec()
        node_ids = {n.node_id for n in spec.nodes}
        assert "integration_assembler" in node_ids
        assert "persist_codegen_output" in node_ids

    def test_codegen_spec_no_legacy_nodes(self):
        spec = get_g4_codegen_subgraph_spec()
        node_ids = {n.node_id for n in spec.nodes}
        legacy = {
            "material_registry_codegen",
            "component_geometry_codegen",
            "placement_codegen",
            "source_codegen",
            "physics_macro_codegen",
            "sensitive_detector_codegen",
            "scoring_codegen",
            "output_manager_codegen",
            "code_module_planner",
            "geometry_builder_plan_node",
        }
        found_legacy = legacy & node_ids
        assert not found_legacy, f"Legacy nodes found: {found_legacy}"

    def test_draw_subgraph_codegen(self):
        diagram = draw_subgraph("g4_codegen")
        assert "flowchart" in diagram

    def test_draw_all_includes_codegen(self):
        diagrams = draw_all()
        assert "g4_codegen" in diagrams

    def test_draw_combined_includes_module_flow(self):
        diagram = draw_combined()
        assert "g4_codegen_subgraph" in diagram
