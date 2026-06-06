"""Tests for score_combined_context_sufficiency — RAG×Web decision matrix."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from agent_core.nodes.score_combined_context_sufficiency import (
    _WEB_SUPPLEMENT_MIN_SCORE,
    score_combined_context_sufficiency,
)


def _make_state(
    rag_score: float = 0.0,
    rag_decision: str = "block_no_context",
    web_score: float = 0.0,
    web_context: list | None = None,
    web_available: bool = False,
    job_id: str = "test-combined",
) -> dict:
    """Build a minimal state dict for testing."""
    return {
        "rag_sufficiency_score": rag_score,
        "context_decision": rag_decision,
        "web_sufficiency_score": web_score,
        "web_context": web_context or [],
        "web_search_available": web_available,
        "job_id": job_id,
    }


class TestDecisionMatrix:
    """All 9 RAG×Web combinations from the decision matrix."""

    @pytest.mark.asyncio
    async def test_rag_allow_rag_ignores_web(self) -> None:
        """RAG allow_rag → final allow_rag regardless of web."""
        state = _make_state(
            rag_score=0.95,
            rag_decision="allow_rag",
            web_score=0.0,
            web_available=False,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "allow_rag"

    @pytest.mark.asyncio
    async def test_rag_allow_rag_with_web_present(self) -> None:
        """RAG allow_rag stays allow_rag even when web is present."""
        state = _make_state(
            rag_score=0.95,
            rag_decision="allow_rag",
            web_score=0.80,
            web_context=[{"url": "https://example.com"}],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "allow_rag"

    @pytest.mark.asyncio
    async def test_needs_web_with_sufficient_web(self) -> None:
        """needs_web + web_score >= 0.30 → allow_with_web_supplement."""
        state = _make_state(
            rag_score=0.70,
            rag_decision="needs_web",
            web_score=0.50,
            web_context=[{"url": "https://example.com"}],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "allow_with_web_supplement"

    @pytest.mark.asyncio
    async def test_needs_web_with_marginal_web(self) -> None:
        """needs_web + web_score exactly at threshold → allow_with_web_supplement."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=_WEB_SUPPLEMENT_MIN_SCORE,
            web_context=[{"url": "https://example.com"}],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "allow_with_web_supplement"

    @pytest.mark.asyncio
    async def test_needs_web_below_web_threshold(self) -> None:
        """needs_web + web_score < 0.30 → block_no_context."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=0.10,
            web_context=[{"url": "https://example.com"}],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"

    @pytest.mark.asyncio
    async def test_needs_web_no_web_available(self) -> None:
        """needs_web + web unavailable → block_no_context."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=0.0,
            web_available=False,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"

    @pytest.mark.asyncio
    async def test_needs_web_empty_web_context(self) -> None:
        """needs_web + web returned nothing → block_no_context."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=0.30,
            web_context=[],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"

    @pytest.mark.asyncio
    async def test_block_no_context_ignores_web(self) -> None:
        """block_no_context → final block_no_context even with good web."""
        state = _make_state(
            rag_score=0.20,
            rag_decision="block_no_context",
            web_score=0.90,
            web_context=[{"url": "https://example.com"}],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"


class TestReportContents:
    """Verify report structure and fields."""

    @pytest.mark.asyncio
    async def test_report_has_web_urls(self) -> None:
        state = _make_state(
            rag_score=0.70,
            rag_decision="needs_web",
            web_score=0.50,
            web_context=[
                {"url": "https://b.com"},
                {"url": "https://a.com"},
                {"url": "https://b.com"},  # duplicate
            ],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        report = result["context_sufficiency_report"]
        # URLs should be deduplicated and sorted
        assert report["web_urls"] == ["https://a.com", "https://b.com"]

    @pytest.mark.asyncio
    async def test_report_has_timestamp(self) -> None:
        state = _make_state(rag_score=0.95, rag_decision="allow_rag")
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        report = result["context_sufficiency_report"]
        assert "timestamp" in report
        assert "T" in report["timestamp"]

    @pytest.mark.asyncio
    async def test_current_node_set(self) -> None:
        state = _make_state(rag_score=0.95, rag_decision="allow_rag")
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["current_node"] == "score_combined_context_sufficiency"
