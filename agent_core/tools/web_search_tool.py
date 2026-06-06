"""Web search tool for supplementing local RAG context."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_RAG_SUFFICIENCY_THRESHOLD = 0.75
_DISCLOSURE = "[WEB SUPPLEMENT — verify independently]"


@dataclass(frozen=True)
class WebResult:
    """Single web search result."""

    title: str
    url: str
    snippet: str
    source_type: str = "web"

    def to_context_entry(self) -> dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": f"{_DISCLOSURE} {self.snippet}",
            "source_type": self.source_type,
        }


class WebSearchTool:
    """Web search tool for external context when local RAG is insufficient.

    Only used as supplement, never as primary source.
    Must disclose when web results are used.
    """

    def __init__(self) -> None:
        self.search_count: int = 0
        self.disclosure_required: bool = True

    async def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        """Search the web for supplementary information.

        Placeholder: integrate with a search provider (e.g. Exa, SerpAPI).
        """
        self.search_count += 1
        logger.info("web search #%d: %r (max_results=%d)", self.search_count, query, max_results)
        # TODO: wire to actual search backend
        return []

    def format_for_context(self, results: list[WebResult]) -> list[dict[str, str]]:
        """Format web results as RAG-compatible context entries with disclosure."""
        return [r.to_context_entry() for r in results]

    def should_use_web(self, rag_sufficiency_score: float) -> bool:
        """Only use web when RAG score is below threshold."""
        return rag_sufficiency_score < _RAG_SUFFICIENCY_THRESHOLD
