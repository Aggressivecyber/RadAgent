"""Artifact Subgraph — collect GitHub-reviewable artifacts."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import collect_artifacts, generate_artifact_manifest, generate_artifact_readme
from .schemas import ArtifactSubgraphState


def build_artifact_subgraph() -> StateGraph:
    """Build the Artifact Collection Subgraph.

    Flow: collect → manifest → readme
    """
    graph = StateGraph(ArtifactSubgraphState)

    graph.add_node("collect_artifacts", collect_artifacts)
    graph.add_node("generate_artifact_manifest", generate_artifact_manifest)
    graph.add_node("generate_artifact_readme", generate_artifact_readme)

    graph.set_entry_point("collect_artifacts")
    graph.add_edge("collect_artifacts", "generate_artifact_manifest")
    graph.add_edge("generate_artifact_manifest", "generate_artifact_readme")
    graph.add_edge("generate_artifact_readme", END)

    return graph
