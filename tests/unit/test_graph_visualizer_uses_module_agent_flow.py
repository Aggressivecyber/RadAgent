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

    def test_codegen_spec_has_module_agents(self):
        spec = get_g4_codegen_subgraph_spec()
        node_ids = {n.node_id for n in spec.nodes}
        assert "run_material_agent" in node_ids
        assert "run_geometry_agent" in node_ids
        assert "run_main_cmake_agent" in node_ids

    def test_codegen_spec_has_module_gates(self):
        spec = get_g4_codegen_subgraph_spec()
        node_ids = {n.node_id for n in spec.nodes}
        assert "material_hard_gate" in node_ids
        assert "material_llm_gate" in node_ids
        assert "geometry_hard_gate" in node_ids

    def test_codegen_spec_has_cross_file_gates(self):
        spec = get_g4_codegen_subgraph_spec()
        node_ids = {n.node_id for n in spec.nodes}
        assert "cross_file_hard_gate" in node_ids
        assert "cross_file_llm_gate" in node_ids
        assert "static_semantic_scanner" in node_ids

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
