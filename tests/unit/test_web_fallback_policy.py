"""Web fallback policy tests.

Validates that web search is only used as supplement (never primary),
and that the tool correctly reports availability and applies disclosure.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from agent_core.tools.web_search_tool import WebResult, WebSearchTool


def test_web_result_to_context_entry_has_disclosure():
    """Every web result entry must carry the disclosure tag."""
    wr = WebResult(
        title="Geant4 Physics",
        url="https://example.com/g4",
        snippet="Some physics reference",
        confidence=0.7,
    )
    entry = wr.to_context_entry()
    assert "WEB SUPPLEMENT" in entry["snippet"]
    assert entry["confidence"] == 0.7
    assert "retrieved_at" in entry


def test_web_result_confidence_defaults_to_zero():
    """Confidence field defaults to 0.0."""
    wr = WebResult(title="t", url="http://x", snippet="s")
    assert wr.confidence == 0.0


def test_should_use_web_below_threshold():
    """Web search recommended when RAG score < 0.75."""
    tool = WebSearchTool()
    assert tool.should_use_web(0.50) is True
    assert tool.should_use_web(0.74) is True


def test_should_not_use_web_above_threshold():
    """Web search NOT recommended when RAG score >= 0.75."""
    tool = WebSearchTool()
    assert tool.should_use_web(0.75) is False
    assert tool.should_use_web(0.95) is False


def test_backend_detection_disabled():
    """When DISABLE_WEB_SEARCH=1, backend is 'none'."""
    with patch.dict(os.environ, {"DISABLE_WEB_SEARCH": "1"}):
        tool = WebSearchTool()
        assert tool._backend == "none"
        assert tool.search_available is False


def test_backend_detection_exa():
    """When EXA_API_KEY is set, backend is 'exa'."""
    with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}, clear=False):
        # Also ensure DDG is not disabled
        env = {"EXA_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=False):
            tool = WebSearchTool()
            assert tool._backend == "exa"
            assert tool.search_available is True


def test_backend_detection_ddg_default():
    """Default backend is duckduckgo when no special env vars."""
    with patch.dict(os.environ, {}, clear=False):
        # Remove any interfering env vars
        env = os.environ.copy()
        env.pop("EXA_API_KEY", None)
        env.pop("DISABLE_WEB_SEARCH", None)
        with patch.dict(os.environ, env, clear=True):
            tool = WebSearchTool()
            assert tool._backend == "duckduckgo"


@pytest.mark.anyio
async def test_search_returns_empty_when_disabled():
    """Search returns [] (not error) when backend is 'none'."""
    with patch.dict(os.environ, {"DISABLE_WEB_SEARCH": "1"}):
        tool = WebSearchTool()
        results = await tool.search("test query")
        assert results == []


def test_format_for_context_includes_disclosure():
    """format_for_context must include disclosure tag on every entry."""
    results = [
        WebResult(title="A", url="http://a", snippet="sa", confidence=0.8),
        WebResult(title="B", url="http://b", snippet="sb", confidence=0.5),
    ]
    tool = WebSearchTool()
    entries = tool.format_for_context(results)
    assert len(entries) == 2
    for entry in entries:
        assert "WEB SUPPLEMENT" in entry["snippet"]
        assert "retrieved_at" in entry
