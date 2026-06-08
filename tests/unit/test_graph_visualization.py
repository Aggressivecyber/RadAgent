"""Tests for graph visualization module."""

from __future__ import annotations

from typing import Any

import pytest
from agent_core.visualization.graph_visualizer import (
    EdgeSpec,
    NodeSpec,
    SubgraphSpec,
    draw_all,
    draw_combined,
    draw_main_graph,
    draw_subgraph,
    export_mermaid,
    get_all_subgraph_specs,
    get_main_graph_spec,
)

# ─── Topology completeness tests ─────────────────────────────────────

class TestMainGraphTopology:
    """Verify main graph topology matches the actual graph code."""

    def test_main_graph_has_9_nodes(self) -> None:
        spec = get_main_graph_spec()
        assert len(spec.nodes) == 9

    def test_main_graph_has_prepare_workspace(self) -> None:
        spec = get_main_graph_spec()
        ids = {n.node_id for n in spec.nodes}
        assert "prepare_workspace" in ids

    def test_main_graph_has_all_subgraphs(self) -> None:
        spec = get_main_graph_spec()
        ids = {n.node_id for n in spec.nodes}
        expected = {
            "context_subgraph",
            "task_planning_subgraph",
            "g4_modeling_subgraph",
            "g4_codegen_subgraph",
            "patch_subgraph",
            "gate_subgraph",
            "artifact_subgraph",
            "report_subgraph",
        }
        assert expected.issubset(ids)

    def test_main_graph_has_entry_point(self) -> None:
        spec = get_main_graph_spec()
        entry_nodes = [n for n in spec.nodes if n.is_entry]
        assert len(entry_nodes) == 1
        assert entry_nodes[0].node_id == "prepare_workspace"

    def test_main_graph_conditional_routes(self) -> None:
        spec = get_main_graph_spec()
        # Gate subgraph has retry routes back to multiple subgraphs
        gate_retries = [
            e for e in spec.conditional_edges
            if e.source == "gate_subgraph" and e.style == "retry"
        ]
        assert len(gate_retries) >= 5  # context, planning, modeling, codegen, patch

        # Verify each retry target
        retry_targets = {e.target for e in gate_retries}
        assert "context_subgraph" in retry_targets
        assert "task_planning_subgraph" in retry_targets
        assert "g4_modeling_subgraph" in retry_targets
        assert "g4_codegen_subgraph" in retry_targets
        assert "patch_subgraph" in retry_targets


class TestSubgraphTopology:
    """Verify each subgraph has the expected number of nodes."""

    @pytest.mark.parametrize(
        "name,expected_nodes",
        [
            ("context", 6),
            ("task_planning", 3),
            ("g4_modeling", 14),
            ("g4_codegen", 52),
            ("gate_validation", 4),
            ("patch", 3),
            ("artifact", 3),
            ("report", 1),
        ],
    )
    def test_node_count(self, name: str, expected_nodes: int) -> None:
        specs = get_all_subgraph_specs()
        assert len(specs[name].nodes) == expected_nodes

    @pytest.mark.parametrize(
        "name",
        ["context", "task_planning", "g4_modeling", "g4_codegen",
         "gate_validation", "patch", "artifact", "report"],
    )
    def test_has_entry_point(self, name: str) -> None:
        specs = get_all_subgraph_specs()
        entry_nodes = [n for n in specs[name].nodes if n.is_entry]
        assert len(entry_nodes) == 1

    @pytest.mark.parametrize(
        "name",
        ["context", "task_planning", "g4_modeling", "g4_codegen",
         "gate_validation", "patch", "artifact", "report"],
    )
    def test_all_edges_reference_valid_nodes(self, name: str) -> None:
        specs = get_all_subgraph_specs()
        spec = specs[name]
        node_ids = {n.node_id for n in spec.nodes} | {"END"}
        for edge in spec.edges:
            assert edge.source in node_ids, f"Edge source {edge.source} not in nodes"
            assert edge.target in node_ids, f"Edge target {edge.target} not in nodes"
        for edge in spec.conditional_edges:
            assert edge.source in node_ids, f"Cond edge source {edge.source} not in nodes"
            assert edge.target in node_ids, f"Cond edge target {edge.target} not in nodes"

    def test_g4_modeling_has_retry_loop(self) -> None:
        specs = get_all_subgraph_specs()
        modeling = specs["g4_modeling"]
        retry_edges = [e for e in modeling.conditional_edges if e.style == "retry"]
        assert len(retry_edges) >= 1
        # Validation can loop back to geometry_decomposition
        targets = {e.target for e in retry_edges}
        assert "geometry_decomposition_node" in targets

    def test_task_planning_has_retry_loop(self) -> None:
        specs = get_all_subgraph_specs()
        planning = specs["task_planning"]
        retry_edges = [e for e in planning.conditional_edges if e.style == "retry"]
        assert len(retry_edges) == 1
        assert retry_edges[0].target == "parse_task"

    def test_context_has_conditional_rag_web(self) -> None:
        specs = get_all_subgraph_specs()
        ctx = specs["context"]
        cond_edges = ctx.conditional_edges
        targets = {e.target for e in cond_edges}
        assert "retrieve_web_context" in targets
        assert "save_evidence_map" in targets

    def test_eight_subgraphs_total(self) -> None:
        assert len(get_all_subgraph_specs()) == 8


# ─── Mermaid renderer tests ──────────────────────────────────────────

class TestMermaidRenderer:
    """Test the Mermaid diagram renderer."""

    def test_render_main_graph_produces_valid_mermaid(self) -> None:
        output = draw_main_graph()
        assert "flowchart TB" in output
        assert "prepare_workspace" in output
        assert "context_subgraph" in output
        assert "report_subgraph" in output

    def test_render_uses_correct_arrow_types(self) -> None:
        output = draw_main_graph()
        # Normal edge
        assert "-->" in output
        # Block edge (thick)
        assert "==>" in output
        # Retry edge (dotted)
        assert "-.->" in output

    def test_render_each_subgraph(self) -> None:
        for name in get_all_subgraph_specs():
            output = draw_subgraph(name)
            assert "flowchart TB" in output, f"Subgraph {name} missing flowchart header"
            spec = get_all_subgraph_specs()[name]
            for node in spec.nodes:
                assert node.node_id in output, f"Node {node.node_id} missing from {name}"

    def test_render_unknown_subgraph_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown subgraph"):
            draw_subgraph("nonexistent")

    def test_draw_all_returns_9_diagrams(self) -> None:
        all_diagrams = draw_all()
        assert len(all_diagrams) == 9  # main + 8 subgraphs
        assert "main_graph" in all_diagrams
        assert "g4_modeling" in all_diagrams

    def test_draw_combined_has_subgraph_blocks(self) -> None:
        output = draw_combined()
        assert "subgraph g4_modeling_subgraph" in output
        assert "subgraph context_subgraph" in output
        assert "direction TB" in output

    def test_render_includes_node_styles(self) -> None:
        output = draw_main_graph()
        assert "classDef" in output
        assert "fill:" in output
        assert "stroke:" in output

    def test_guard_nodes_use_hexagon_shape(self) -> None:
        """Guard/gate nodes should use {{ }} (hexagon) shape."""
        output = draw_subgraph("g4_modeling")
        # model_scope_guard_node should use hexagon shape
        assert "model_scope_guard_node{{" in output

    def test_io_nodes_use_square_shape(self) -> None:
        """I/O nodes should use [ ] (square) shape."""
        output = draw_subgraph("g4_modeling")
        # load_task_spec is an I/O node
        assert "load_task_spec[" in output

    def test_end_node_uses_circle_shape(self) -> None:
        """END nodes should use (( )) (circle) shape."""
        output = draw_main_graph()
        assert "END((END))" in output


class TestExportMermaid:
    """Test file export functionality."""

    def test_export_creates_files(self, tmp_path: Any) -> None:
        written = export_mermaid(output_dir=tmp_path, combined=True, individual=True)
        assert len(written) >= 9
        for path in written:
            assert path.exists()
            assert path.suffix == ".mmd"
            assert path.stat().st_size > 0

    def test_export_individual_only(self, tmp_path: Any) -> None:
        written = export_mermaid(output_dir=tmp_path, combined=False, individual=True)
        names = {p.name for p in written}
        assert "main_graph.mmd" in names
        assert "g4_modeling.mmd" in names
        assert "radagent_graph_overview.mmd" not in names

    def test_export_combined_only(self, tmp_path: Any) -> None:
        written = export_mermaid(output_dir=tmp_path, combined=True, individual=False)
        names = {p.name for p in written}
        assert "radagent_graph_overview.mmd" in names
        assert len(written) == 1


# ─── Data model tests ────────────────────────────────────────────────

class TestDataModel:
    """Test frozen dataclasses."""

    def test_node_spec_frozen(self) -> None:
        node = NodeSpec("id", "label", "core")
        with pytest.raises(AttributeError):
            node.node_id = "changed"  # type: ignore[misc]

    def test_edge_spec_frozen(self) -> None:
        edge = EdgeSpec("a", "b")
        with pytest.raises(AttributeError):
            edge.source = "c"  # type: ignore[misc]

    def test_subgraph_spec_frozen(self) -> None:
        spec = SubgraphSpec("n", "d", "desc", (), ())
        with pytest.raises(AttributeError):
            spec.name = "x"  # type: ignore[misc]
