"""Context subgraph schemas — input/output and internal state."""

from __future__ import annotations

from typing import Any, TypedDict


class ContextSubgraphInput(TypedDict, total=False):
    """Input to the Context Subgraph."""

    job_id: str
    user_query: str
    required_sources: list[str]  # e.g. ["geant4"]


class ContextSubgraphOutput(TypedDict, total=False):
    """Output from the Context Subgraph."""

    context_decision: str  # "allow_rag" | "allow_with_web_supplement" | "block_no_context"
    context_report_path: str
    evidence_map_path: str


class ContextSubgraphState(TypedDict, total=False):
    """Internal state for Context Subgraph nodes."""

    job_id: str
    user_query: str
    required_sources: list[str]

    # RAG results
    user_context_requirements: dict[str, Any]
    rag_context: list[dict[str, Any]]
    rag_score: float
    rag_report: dict[str, Any]

    # Web results
    web_context: list[dict[str, Any]]
    web_urls: list[str]
    web_search_available: bool

    # Combined
    context_decision: str
    context_report_path: str
    evidence_map_path: str

    # Routing
    needs_web_supplement: bool
