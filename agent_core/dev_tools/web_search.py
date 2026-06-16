"""Web search dev tool for agentic codegen loops."""

from __future__ import annotations

from typing import Any

from agent_core.tools.web_search_tool import WebSearchTool


async def search_web(query: str, *, top_k: int = 5) -> dict[str, Any]:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return {"ok": False, "error": "query must be non-empty."}

    tool = WebSearchTool()
    if not tool.search_available:
        return {"ok": False, "error": "Web search backend unavailable."}

    try:
        results = await tool.search(
            normalized_query,
            max_results=max(1, min(int(top_k or 5), 10)),
        )
    except Exception as exc:
        return {"ok": False, "error": f"Web search failed: {exc}"}

    return {
        "ok": True,
        "query": normalized_query,
        "results": [
            {
                "title": result.title,
                "url": result.url,
                "snippet": result.snippet,
                "source_type": result.source_type,
                "confidence": round(float(result.confidence), 4),
            }
            for result in results
        ],
    }
