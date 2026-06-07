"""Graph visualization module for RadAgent.

Generates Mermaid diagrams of the main graph and all subgraphs,
with color-coded nodes, conditional route labels, and retry loop styling.

Usage:
    # From Python
    from agent_core.visualization import (
        draw_main_graph,
        draw_subgraph,
        draw_all,
        export_mermaid,
    )

    # From CLI
    python -m agent_core.visualization draw          # all graphs
    python -m agent_core.visualization draw --main    # main graph only
    python -m agent_core.visualization draw --sub g4_modeling
"""

from agent_core.visualization.graph_visualizer import (
    MermaidRenderer,
    SubgraphSpec,
    draw_all,
    draw_main_graph,
    draw_subgraph,
    export_mermaid,
)

__all__ = [
    "MermaidRenderer",
    "SubgraphSpec",
    "draw_all",
    "draw_main_graph",
    "draw_subgraph",
    "export_mermaid",
]
