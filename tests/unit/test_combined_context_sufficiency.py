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
    rag_required: list | None = None,
) -> dict:
    """Build a minimal state dict for testing."""
    return {
        "rag_sufficiency_score": rag_score,
        "context_decision": rag_decision,
        "web_sufficiency_score": web_score,
        "web_context": web_context or [],
        "web_search_available": web_available,
        "job_id": job_id,
        "rag_required_sources": rag_required or ["geant4"],
    }


# Minimal web context that passes all criteria:
# - 2 valid URLs
# - 1 official source (github.com)
# - keyword hit ("geant4" in title)
_PASSING_WEB_CONTEXT = [
    {
        "url": "https://github.com/Geant4/geant4",
        "title": "Geant4 Simulation Toolkit",
        "snippet": "Geant4 physics simulation reference",
        "confidence": 0.8,
    },
    {
        "url": "https://example.com/physics",
        "title": "Simulation tutorial",
        "snippet": "Tutorial on simulation techniques",
        "confidence": 0.5,
    },
]


class TestDecisionMatrix:
    """All RAG×Web combinations from the decision matrix."""

    @pytest.mark.anyio
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

    @pytest.mark.anyio
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

    @pytest.mark.anyio
    async def test_needs_web_with_sufficient_web(self) -> None:
        """needs_web + web meets all criteria → allow_with_web_supplement."""
        state = _make_state(
            rag_score=0.70,
            rag_decision="needs_web",
            web_score=0.50,
            web_context=_PASSING_WEB_CONTEXT,
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "allow_with_web_supplement"

    @pytest.mark.anyio
    async def test_needs_web_with_marginal_web(self) -> None:
        """needs_web + web at threshold + criteria met → allow_with_web_supplement."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=_WEB_SUPPLEMENT_MIN_SCORE,
            web_context=_PASSING_WEB_CONTEXT,
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "allow_with_web_supplement"

    @pytest.mark.anyio
    async def test_needs_web_below_web_threshold(self) -> None:
        """needs_web + web_score < 0.30 → block_no_context."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=0.10,
            web_context=_PASSING_WEB_CONTEXT,
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"

    @pytest.mark.anyio
    async def test_needs_web_only_one_url(self) -> None:
        """needs_web + only 1 URL (< 2 required) → block_no_context."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=0.50,
            web_context=[
                {
                    "url": "https://github.com/test",
                    "title": "Geant4 simulation",
                    "snippet": "Physics simulation",
                    "confidence": 0.7,
                },
            ],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"

    @pytest.mark.anyio
    async def test_needs_web_no_official_source(self) -> None:
        """needs_web + 2 URLs but no official source → block_no_context."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=0.50,
            web_context=[
                {
                    "url": "https://random-blog.com/g4",
                    "title": "Geant4 simulation",
                    "snippet": "Physics simulation",
                    "confidence": 0.7,
                },
                {
                    "url": "https://another-blog.com/g4",
                    "title": "More geant4",
                    "snippet": "More physics simulation",
                    "confidence": 0.6,
                },
            ],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"

    @pytest.mark.anyio
    async def test_needs_web_no_keyword_hit(self) -> None:
        """needs_web + 2 URLs + official but no keyword → block_no_context."""
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=0.50,
            web_context=[
                {
                    "url": "https://github.com/random/project",
                    "title": "Unrelated project",
                    "snippet": "Something unrelated",
                    "confidence": 0.7,
                },
                {
                    "url": "https://cern.ch/other",
                    "title": "Other topic",
                    "snippet": "Different content",
                    "confidence": 0.6,
                },
            ],
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"

    @pytest.mark.anyio
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

    @pytest.mark.anyio
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

    @pytest.mark.anyio
    async def test_block_no_context_ignores_web(self) -> None:
        """block_no_context → final block_no_context even with good web."""
        state = _make_state(
            rag_score=0.20,
            rag_decision="block_no_context",
            web_score=0.90,
            web_context=_PASSING_WEB_CONTEXT,
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["context_decision"] == "block_no_context"


class TestReportContents:
    """Verify report structure and fields."""

    @pytest.mark.anyio
    async def test_report_has_web_urls(self) -> None:
        state = _make_state(
            rag_score=0.70,
            rag_decision="needs_web",
            web_score=0.50,
            web_context=_PASSING_WEB_CONTEXT,
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        report = result["context_sufficiency_report"]
        assert report["web_urls"] == [
            "https://example.com/physics",
            "https://github.com/Geant4/geant4",
        ]

    @pytest.mark.anyio
    async def test_report_has_timestamp(self) -> None:
        state = _make_state(rag_score=0.95, rag_decision="allow_rag")
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        report = result["context_sufficiency_report"]
        assert "timestamp" in report
        assert "T" in report["timestamp"]

    @pytest.mark.anyio
    async def test_report_has_used_for(self) -> None:
        state = _make_state(
            rag_score=0.70,
            rag_decision="needs_web",
            web_score=0.50,
            web_context=_PASSING_WEB_CONTEXT,
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        report = result["context_sufficiency_report"]
        assert "used_for" in report
        assert len(report["used_for"]) == 2
        for entry in report["used_for"]:
            assert "url" in entry
            assert entry["used_for"] == "supplement"

    @pytest.mark.anyio
    async def test_report_has_web_fail_reason(self) -> None:
        state = _make_state(
            rag_score=0.65,
            rag_decision="needs_web",
            web_score=0.10,
            web_context=_PASSING_WEB_CONTEXT,
            web_available=True,
        )
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        report = result["context_sufficiency_report"]
        assert report["decision"] == "block_no_context"
        assert "web_fail_reason" in report

    @pytest.mark.anyio
    async def test_current_node_set(self) -> None:
        state = _make_state(rag_score=0.95, rag_decision="allow_rag")
        with patch(
            "agent_core.nodes.score_combined_context_sufficiency.get_job_dir"
        ):
            result = await score_combined_context_sufficiency(state)
        assert result["current_node"] == "score_combined_context_sufficiency"
