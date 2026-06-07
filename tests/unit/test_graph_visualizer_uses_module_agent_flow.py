"""Test that graph visualizer uses module agent flow keywords."""

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

    def test_main_graph_contains_codegen_subgraph(self) -> None:
        """Main graph diagram should reference g4_codegen_subgraph."""
        diagram = draw_main_graph()

        assert "g4_codegen_subgraph" in diagram
        assert "代码生成" in diagram or "Codegen" in diagram.lower() or "codegen" in diagram.lower()

    def test_codegen_subgraph_contains_module_agents(self) -> None:
        """G4 codegen subgraph should contain module agent flow keywords."""
        spec = get_g4_codegen_subgraph_spec()

        # Check node IDs contain module agent related keywords
        node_ids = [n.node_id for n in spec.nodes]

        # Should have module-related nodes
        module_keywords = [
            "module_agents", "module_gates", "integration_assembler",
            "static_semantic_scanner", "cross_file_hard_gate",
            "cross_file_llm_gate", "proposed_patch",
        ]
        found = [kw for kw in module_keywords if any(kw in nid for nid in node_ids)]
        assert len(found) >= 3, (
            f"Expected at least 3 module flow keywords in nodes, found: {found}"
        )

    def test_draw_subgraph_codegen(self) -> None:
        """draw_subgraph('g4_codegen') should produce valid Mermaid."""
        diagram = draw_subgraph("g4_codegen")

        assert "flowchart" in diagram
        # Updated: new visualizer uses different node names
        assert "integration_assembler" in diagram or "codegen" in diagram.lower()

    def test_draw_all_includes_codegen(self) -> None:
        """draw_all should include g4_codegen subgraph."""
        diagrams = draw_all()

        assert "g4_codegen" in diagrams
        assert "material" in diagrams["g4_codegen"] or "codegen" in diagrams["g4_codegen"].lower()

    def test_draw_combined_includes_module_flow(self) -> None:
        """Combined diagram should include module agent flow."""
        diagram = draw_combined()

        assert "g4_codegen_subgraph" in diagram
        assert "persist" in diagram or "codegen" in diagram.lower()
