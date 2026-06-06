"""Tests for score_rag_sufficiency — tri-state decision, no fake 0.76 override."""

from __future__ import annotations

import pytest
from agent_core.nodes.score_rag_sufficiency import _compute_score


class TestComputeScoreEmptyContext:
    """Empty RAG must always produce score 0.0 and block_no_context."""

    def test_all_empty_returns_zero(self) -> None:
        score, report = _compute_score([], [], [])
        assert score == 0.0
        assert report["decision"] == "block_no_context"

    def test_no_fake_override(self) -> None:
        """Historically score=0.0 was bumped to 0.76 — must NOT happen."""
        score, report = _compute_score([], [], [])
        assert score == 0.0, f"Score was overridden to {score}"

    def test_required_sources_dont_change_empty_score(self) -> None:
        score, report = _compute_score([], [], [], required_sources=["geant4"])
        assert score == 0.0
        assert report["decision"] == "block_no_context"
        assert "geant4" in report.get("missing_required_sources", [])


class TestComputeScoreAllowRAG:
    """Sufficient context should produce allow_rag."""

    @pytest.fixture
    def rich_context(self) -> list[dict]:
        """Context that scores high enough for allow_rag."""
        return [
            {"source_type": "manual", "source": "Geant4 Manual", "code": "example"},
            {"source_type": "example_code", "source": "examples/"},
            {"source_type": "data_contract", "source": "contract info"},
        ]

    def test_rich_context_allows_rag(self, rich_context: list[dict]) -> None:
        score, report = _compute_score(rich_context, [], [])
        assert score >= 0.90
        assert report["decision"] == "allow_rag"
        assert report["has_manual"] is True
        assert report["has_examples"] is True
        assert report["has_contracts"] is True

    def test_rich_with_missing_required_caps_score(
        self, rich_context: list[dict],
    ) -> None:
        """Required source missing → score capped below allow_rag threshold."""
        score, report = _compute_score(
            rich_context, [], [],
            required_sources=["tcad"],  # tcad is empty
        )
        assert score <= 0.55, f"Score {score} should be capped at 0.55"
        assert report["decision"] != "allow_rag"


class TestComputeScoreNeedsWeb:
    """Partial context should produce needs_web (score 0.60–0.89)."""

    def test_partial_context_needs_web(self) -> None:
        """Only manual + base → 0.45, not enough for allow_rag."""
        ctx = [{"source_type": "manual", "source": "manual section"}]
        score, report = _compute_score(ctx, [], [])
        # manual=0.30 + base=0.15 = 0.45 → block_no_context (<0.60)
        assert score == 0.45
        assert report["decision"] == "block_no_context"

    def test_manual_plus_examples_needs_web(self) -> None:
        """manual + examples + base = 0.70 → needs_web."""
        ctx = [
            {"source_type": "manual", "source": "manual"},
            {"source_type": "example_code", "source": "code example"},
        ]
        score, report = _compute_score(ctx, [], [])
        # manual=0.30 + examples=0.25 + base=0.15 = 0.70
        assert 0.60 <= score < 0.90
        assert report["decision"] == "needs_web"


class TestComputeScoreDecisionBoundaries:
    """Verify exact threshold behavior."""

    def test_block_no_context_below_60(self) -> None:
        """Any score < 0.60 must be block_no_context."""
        # Only base score (any context present) = 0.15
        ctx = [{"source": "generic", "content": "something"}]
        score, report = _compute_score(ctx, [], [])
        assert score == 0.15
        assert report["decision"] == "block_no_context"

    def test_report_has_missing_items(self) -> None:
        """Report should list what's missing."""
        score, report = _compute_score([], [], [])
        assert len(report["missing_items"]) > 0
        assert any("No context" in item for item in report["missing_items"])

    def test_missing_items_for_partial(self) -> None:
        """Partial context lists what categories are absent."""
        ctx = [{"source_type": "manual", "source": "manual"}]
        _, report = _compute_score(ctx, [], [])
        assert any("example" in item.lower() for item in report["missing_items"])
        assert any("contract" in item.lower() for item in report["missing_items"])
