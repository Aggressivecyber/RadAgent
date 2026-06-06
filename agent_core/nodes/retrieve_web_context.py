"""Retrieve web context to supplement insufficient RAG.

Activated when score_rag_sufficiency returns 'needs_web'.
Saves results to 01_context/web_context.json.
"""

from __future__ import annotations

import json

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState
from agent_core.tools.web_search_tool import WebSearchTool


async def retrieve_web_context(state: RadiationAgentState) -> dict:
    """Search the web for supplementary context when RAG is insufficient.

    Constructs queries from the user request and RAG missing_items,
    searches via WebSearchTool, saves structured results.
    """
    job_id = state.get("job_id", "unknown")
    user_query = state.get("user_query", "")
    rag_report = state.get("rag_sufficiency_report", {})

    tool = WebSearchTool()
    all_results: list[dict] = []
    seen_urls: set[str] = set()

    # Build queries: primary from user, supplemental from RAG missing items
    queries = [user_query]
    missing_items = rag_report.get("missing_items", [])
    for item in missing_items[:3]:
        queries.append(f"{user_query} {item}")

    for query in queries[:4]:  # Max 4 queries
        try:
            results = await tool.search(query, max_results=3)
            for r in results:
                # Deduplicate by URL
                if r.url in seen_urls:
                    continue
                seen_urls.add(r.url)
                entry = r.to_context_entry()
                entry["query_used"] = query
                all_results.append(entry)
        except Exception:
            continue

    # Save context file
    job_dir = get_job_dir(job_id)
    ctx_file = job_dir / "01_context" / "web_context.json"
    ctx_file.write_text(json.dumps(all_results, indent=2, ensure_ascii=False))

    # Web sufficiency: simple heuristic — need at least 3 distinct results
    web_score = min(1.0, len(all_results) / 10.0)

    return {
        "web_context": all_results,
        "web_sufficiency_score": web_score,
        "web_search_available": tool.search_available,
        "current_node": "retrieve_web_context",
    }
