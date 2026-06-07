"""Web search tool for supplementing local RAG context.

Backends:
  - DuckDuckGo HTML (default, no API key required)
  - Exa API (optional, requires EXA_API_KEY env var)

Proxy:
  - Set RADAGENT_PROXY (e.g. "http://127.0.0.1:7892") to route requests
    through a local proxy like mihomo/Clash.
  - Falls back to http_proxy / https_proxy / ALL_PROXY env vars.

Set DISABLE_WEB_SEARCH=1 to disable all web search.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import unquote

logger = logging.getLogger(__name__)

_RAG_SUFFICIENCY_THRESHOLD = 0.75
_DISCLOSURE = "[WEB SUPPLEMENT — verify independently]"

# Lightweight HTML tag stripper
_STRIP_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    return _STRIP_RE.sub("", text).strip()


@dataclass(frozen=True)
class WebResult:
    """Single web search result."""

    title: str
    url: str
    snippet: str
    source_type: str = "web"
    confidence: float = 0.0

    def to_context_entry(self) -> dict[str, str | float]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": f"{_DISCLOSURE} {self.snippet}",
            "source_type": self.source_type,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "confidence": self.confidence,
        }


class WebSearchTool:
    """Web search tool with DuckDuckGo (default) and Exa (optional) backends.

    Only used as supplement to RAG, never as primary source.
    All web results carry mandatory disclosure tags.

    Proxy configuration (priority order):
      1. RADAGENT_PROXY env var (e.g. "http://127.0.0.1:7892")
      2. http_proxy / https_proxy / ALL_PROXY env vars
      3. No proxy (direct connection)
    """

    def __init__(self) -> None:
        self.search_count: int = 0
        self.disclosure_required: bool = True
        self._backend: str = self._detect_backend()
        self._proxy: str | None = self._detect_proxy()

    def _detect_proxy(self) -> str | None:
        """Detect proxy from environment variables."""
        proxy = os.environ.get("RADAGENT_PROXY")
        if proxy:
            return proxy
        proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
        if proxy:
            return proxy
        proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
        if proxy:
            return proxy
        proxy = os.environ.get("ALL_PROXY")
        if proxy:
            return proxy
        return None

    @property
    def search_available(self) -> bool:
        """True when at least one search backend is configured."""
        return self._backend != "none"

    def _detect_backend(self) -> str:
        """Detect available search backend from environment."""
        if os.environ.get("DISABLE_WEB_SEARCH", "").lower() in ("1", "true"):
            return "none"
        if os.environ.get("EXA_API_KEY"):
            return "exa"
        return "duckduckgo"

    async def search(self, query: str, max_results: int = 5) -> list[WebResult]:
        """Search using the configured backend.

        Returns empty list (not error) when backend is unavailable or
        search fails — graceful degradation.
        """
        self.search_count += 1
        logger.info(
            "web search #%d [backend=%s]: %r (max=%d)",
            self.search_count, self._backend, query, max_results,
        )
        if self._backend == "exa":
            return await self._search_exa(query, max_results)
        if self._backend == "duckduckgo":
            return await self._search_duckduckgo(query, max_results)
        logger.warning("No web search backend configured")
        return []

    # ------------------------------------------------------------------
    # DuckDuckGo HTML backend (no API key)
    # ------------------------------------------------------------------

    async def _search_duckduckgo(
        self, query: str, max_results: int,
    ) -> list[WebResult]:
        """DuckDuckGo HTML search via httpx. No API key needed."""
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not installed, DuckDuckGo search unavailable")
            return []

        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
        }
        try:
            async with httpx.AsyncClient(
                timeout=15.0, follow_redirects=True, proxy=self._proxy,
            ) as client:
                resp = await client.post(
                    url, data={"q": query, "b": ""}, headers=headers,
                )
                resp.raise_for_status()
                return self._parse_ddg_html(resp.text, max_results)
        except Exception:
            logger.warning("DuckDuckGo search failed", exc_info=True)
            return []

    @staticmethod
    def _parse_ddg_html(html: str, max_results: int) -> list[WebResult]:
        """Parse DuckDuckGo HTML results page."""
        results: list[WebResult] = []
        # DDG HTML uses result__a for title/link, result__snippet for snippet
        # Split on result blocks
        blocks = re.split(r'class="result\s', html)
        for block in blocks[1:]:  # skip preamble before first result
            if len(results) >= max_results:
                break
            try:
                # Extract URL from first href in result__a
                title_match = re.search(
                    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    block, re.DOTALL,
                )
                if not title_match:
                    continue
                raw_url = title_match.group(1)
                title = _strip_html(title_match.group(2))

                # DDG wraps URLs through redirect; extract actual URL
                url_match = re.search(r"uddg=([^&]+)", raw_url)
                url = (
                    unquote(_strip_html(url_match.group(1)))
                    if url_match else raw_url
                )

                # Extract snippet
                snippet_match = re.search(
                    r'class="result__snippet"[^>]*>(.*?)</[at]',
                    block, re.DOTALL,
                )
                snippet = (
                    _strip_html(snippet_match.group(1))[:300]
                    if snippet_match else ""
                )

                if title and url.startswith("http"):
                    results.append(
                        WebResult(title=title, url=url, snippet=snippet)
                    )
            except Exception:
                continue
        return results

    # ------------------------------------------------------------------
    # Exa API backend (optional)
    # ------------------------------------------------------------------

    async def _search_exa(self, query: str, max_results: int) -> list[WebResult]:
        """Exa API search. Requires EXA_API_KEY environment variable."""
        import httpx

        api_key = os.environ.get("EXA_API_KEY", "")
        if not api_key:
            logger.warning("EXA_API_KEY not set, falling back to DuckDuckGo")
            return await self._search_duckduckgo(query, max_results)

        try:
            async with httpx.AsyncClient(
                timeout=15.0, proxy=self._proxy,
            ) as client:
                resp = await client.post(
                    "https://api.exa.ai/search",
                    json={
                        "query": query,
                        "numResults": max_results,
                        "type": "auto",
                        "contents": {"text": {"maxCharacters": 300}},
                    },
                    headers={
                        "x-api-key": api_key,
                        "Content-Type": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return [
                    WebResult(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("text", "")[:300],
                    )
                    for r in data.get("results", [])
                    if r.get("url")
                ]
        except Exception:
            logger.warning("Exa search failed", exc_info=True)
            return []

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def format_for_context(self, results: list[WebResult]) -> list[dict[str, str | float]]:
        """Format web results as RAG-compatible context entries with disclosure."""
        return [r.to_context_entry() for r in results]

    def should_use_web(self, rag_sufficiency_score: float) -> bool:
        """Only use web when RAG score is below threshold."""
        return rag_sufficiency_score < _RAG_SUFFICIENCY_THRESHOLD
