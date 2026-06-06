"""Tests for WebSearchTool — DDG backend, disclosure tags, backend detection."""

from __future__ import annotations

import os
from unittest.mock import patch

from agent_core.tools.web_search_tool import (
    WebResult,
    WebSearchTool,
    _strip_html,
)


class TestWebResult:
    """WebResult dataclass and disclosure behavior."""

    def test_to_context_entry_has_disclosure(self) -> None:
        r = WebResult(title="Test", url="https://example.com", snippet="info")
        entry = r.to_context_entry()
        assert "WEB SUPPLEMENT" in entry["snippet"]
        assert entry["source_type"] == "web"

    def test_to_context_entry_has_timestamp(self) -> None:
        r = WebResult(title="Test", url="https://example.com", snippet="info")
        entry = r.to_context_entry()
        assert "retrieved_at" in entry
        assert "T" in entry["retrieved_at"]  # ISO format contains T

    def test_to_context_entry_preserves_title_and_url(self) -> None:
        r = WebResult(title="My Title", url="https://example.com", snippet="desc")
        entry = r.to_context_entry()
        assert entry["title"] == "My Title"
        assert entry["url"] == "https://example.com"


class TestStripHTML:
    """HTML tag stripping utility."""

    def test_strips_tags(self) -> None:
        assert _strip_html("<b>hello</b>") == "hello"

    def test_strips_nested_tags(self) -> None:
        assert _strip_html("<div><p>text</p></div>") == "text"

    def test_empty_string(self) -> None:
        assert _strip_html("") == ""

    def test_no_tags(self) -> None:
        assert _strip_html("plain text") == "plain text"


class TestBackendDetection:
    """Backend auto-detection from environment variables."""

    def test_default_is_duckduckgo(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            tool = WebSearchTool()
            assert tool._backend == "duckduckgo"
            assert tool.search_available is True

    def test_exa_backend_when_key_set(self) -> None:
        with patch.dict(os.environ, {"EXA_API_KEY": "test-key"}, clear=True):
            tool = WebSearchTool()
            assert tool._backend == "exa"
            assert tool.search_available is True

    def test_disabled_via_env(self) -> None:
        with patch.dict(os.environ, {"DISABLE_WEB_SEARCH": "1"}, clear=True):
            tool = WebSearchTool()
            assert tool._backend == "none"
            assert tool.search_available is False

    def test_disabled_via_true_string(self) -> None:
        with patch.dict(os.environ, {"DISABLE_WEB_SEARCH": "true"}, clear=True):
            tool = WebSearchTool()
            assert tool._backend == "none"


class TestParseDDGHTML:
    """DuckDuckGo HTML parsing."""

    def test_parse_valid_html(self) -> None:
        html = """
        <div class="result ">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">
                Example Title
            </a>
            <a class="result__snippet">Example snippet text</a>
        </div>
        """
        results = WebSearchTool._parse_ddg_html(html, max_results=5)
        assert len(results) == 1
        assert results[0].title == "Example Title"
        assert results[0].url == "https://example.com/page"
        assert "Example snippet" in results[0].snippet

    def test_parse_empty_html(self) -> None:
        results = WebSearchTool._parse_ddg_html("", max_results=5)
        assert results == []

    def test_parse_max_results_limit(self) -> None:
        block = """
        <div class="result ">
            <a class="result__a" href="https://example.com/{i}">Title {i}</a>
        </div>
        """
        html = "".join(block.format(i=i) for i in range(10))
        results = WebSearchTool._parse_ddg_html(html, max_results=3)
        assert len(results) <= 3

    def test_parse_no_url_skip(self) -> None:
        """Results without valid URLs should be skipped."""
        html = """
        <div class="result ">
            <a class="result__a" href="javascript:void(0)">No URL</a>
        </div>
        """
        results = WebSearchTool._parse_ddg_html(html, max_results=5)
        assert len(results) == 0


class TestShouldUseWeb:
    """Web search threshold logic."""

    def test_use_web_below_threshold(self) -> None:
        tool = WebSearchTool()
        assert tool.should_use_web(0.50) is True

    def test_no_web_above_threshold(self) -> None:
        tool = WebSearchTool()
        assert tool.should_use_web(0.80) is False

    def test_no_web_at_threshold(self) -> None:
        tool = WebSearchTool()
        assert tool.should_use_web(0.75) is False


class TestFormatForContext:
    """format_for_context returns properly tagged entries."""

    def test_format_includes_disclosure(self) -> None:
        tool = WebSearchTool()
        results = [WebResult(title="T", url="https://x.com", snippet="S")]
        entries = tool.format_for_context(results)
        assert len(entries) == 1
        assert "WEB SUPPLEMENT" in entries[0]["snippet"]

    def test_format_empty(self) -> None:
        tool = WebSearchTool()
        assert tool.format_for_context([]) == []
