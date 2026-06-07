"""Context Subgraph nodes — RAG retrieval, web search, evidence management.

Rules:
1. RAG first
2. RAG insufficient → Web supplement
3. Both insufficient → block_no_context
4. Never use model built-in knowledge as sole source
5. All web results must have URLs
6. All evidence goes to evidence_map
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir

from .schemas import ContextSubgraphState


def _get_context_dir(job_id: str) -> Path:
    """Return the context directory for a job."""
    return get_job_dir(job_id) / "01_context"


async def route_sources(state: ContextSubgraphState) -> dict[str, Any]:
    """Determine which RAG sources to query based on required_sources."""
    required = state.get("required_sources", ["geant4"])
    return {
        "required_sources": required,
    }


async def retrieve_rag_context(state: ContextSubgraphState) -> dict[str, Any]:
    """Retrieve context from Geant4 RAG (MCP tool).

    Uses the geant4-rag MCP server to query domain-specific docs.
    """
    user_query = state.get("user_query", "")
    context_dir = _get_context_dir(state.get("job_id", "unknown"))
    context_dir.mkdir(parents=True, exist_ok=True)

    rag_context: list[dict[str, Any]] = []
    rag_report: dict[str, Any] = {"source": "geant4_rag", "queries": []}

    try:
        from agent_core.llm import get_llm

        llm = get_llm()
        # Use LLM to generate search queries from user query
        query_prompt = (
            f"Generate 3 specific Geant4 documentation search queries "
            f"for this request:\n{user_query}\n\n"
            f"Return as JSON array of strings."
        )
        response = await llm.ainvoke(query_prompt)
        try:
            raw = response.content if hasattr(response, "content") else str(response)
            queries = json.loads(str(raw))
            if isinstance(queries, list):
                queries = [str(q) for q in queries]
            else:
                queries = [user_query]
        except (json.JSONDecodeError, TypeError):
            queries = [user_query]

        rag_report["queries"] = queries

        # RAG retrieval happens via MCP geant4-rag server at orchestration level.
        # In the subgraph, we record the queries for the evidence map.
        # Actual RAG context is populated by the evidence_retrieval_node
        # in the G4 Modeling subgraph.
        rag_report["note"] = (
            "RAG queries generated; actual retrieval via MCP geant4-rag "
            "in g4_modeling subgraph"
        )

    except Exception as e:
        rag_report["error"] = str(e)

    # Save RAG context
    (context_dir / "rag_context.json").write_text(
        json.dumps(rag_context, indent=2, ensure_ascii=False)
    )

    # Score based on context richness
    score = min(1.0, len(rag_context) / 10.0) if rag_context else 0.0
    rag_report["score"] = score
    (context_dir / "rag_sufficiency.json").write_text(
        json.dumps(rag_report, indent=2, ensure_ascii=False)
    )

    needs_web = score < 0.5

    return {
        "rag_context": rag_context,
        "rag_score": score,
        "rag_report": rag_report,
        "needs_web_supplement": needs_web,
    }


async def score_rag_context(state: ContextSubgraphState) -> dict[str, Any]:
    """Score RAG context sufficiency."""
    score = state.get("rag_score", 0.0)
    needs_web = score < 0.5

    if score >= 0.7:
        decision = "allow_rag"
    elif needs_web:
        decision = "needs_web"  # Internal signal, not final
    else:
        decision = "allow_rag"

    return {
        "context_decision": decision if not needs_web else "needs_web",
        "needs_web_supplement": needs_web,
    }


async def retrieve_web_context(state: ContextSubgraphState) -> dict[str, Any]:
    """Retrieve supplementary context from web search."""
    user_query = state.get("user_query", "")
    context_dir = _get_context_dir(state.get("job_id", "unknown"))
    context_dir.mkdir(parents=True, exist_ok=True)

    web_context: list[dict[str, Any]] = []
    web_urls: list[str] = []
    web_available = False

    try:
        from agent_core.tools.web_search_tool import WebSearchTool

        tool = WebSearchTool()
        results = await tool.search(f"Geant4 {user_query} simulation tutorial")
        web_available = True
        for r in results[:5]:
            entry = {
                "title": getattr(r, "title", ""),
                "url": getattr(r, "url", ""),
                "snippet": getattr(r, "snippet", ""),
            }
            web_context.append(entry)
            if entry["url"]:
                web_urls.append(entry["url"])
    except Exception:
        web_available = False

    # Save web context
    (context_dir / "web_context.json").write_text(
        json.dumps(web_context, indent=2, ensure_ascii=False)
    )

    return {
        "web_context": web_context,
        "web_urls": web_urls,
        "web_search_available": web_available,
    }


async def score_combined_context(state: ContextSubgraphState) -> dict[str, Any]:
    """Score combined RAG + Web context and make final decision."""
    rag_score = state.get("rag_score", 0.0)
    web_context = state.get("web_context", [])
    web_urls = state.get("web_urls", [])
    _web_available = state.get("web_search_available", False)  # noqa: F841

    context_dir = _get_context_dir(state.get("job_id", "unknown"))

    # Combined scoring
    web_bonus = min(0.3, len(web_context) * 0.06)
    combined_score = rag_score + web_bonus

    if combined_score >= 0.5:
        decision = "allow_with_web_supplement" if web_context else "allow_rag"
    elif rag_score >= 0.3:
        decision = "allow_with_web_supplement"
    else:
        decision = "block_no_context"

    report = {
        "rag_score": rag_score,
        "web_results": len(web_context),
        "web_urls": web_urls,
        "combined_score": combined_score,
        "decision": decision,
    }

    (context_dir / "context_sufficiency_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )

    return {
        "context_decision": decision,
        "context_report_path": str(context_dir / "context_sufficiency_report.json"),
    }


async def save_evidence_map(state: ContextSubgraphState) -> dict[str, Any]:
    """Save the combined evidence map to disk."""
    context_dir = _get_context_dir(state.get("job_id", "unknown"))
    context_dir.mkdir(parents=True, exist_ok=True)

    evidence_map = {
        "job_id": state.get("job_id", ""),
        "rag_sources": [
            {"type": "rag", "source": "geant4_rag", "items": state.get("rag_context", [])}
        ],
        "web_sources": [
            {
                "type": "web",
                "urls": state.get("web_urls", []),
                "items": state.get("web_context", []),
            }
        ],
        "decision": state.get("context_decision", "block_no_context"),
    }

    path = context_dir / "evidence_map.json"
    path.write_text(json.dumps(evidence_map, indent=2, ensure_ascii=False))

    return {
        "evidence_map_path": str(path),
    }
