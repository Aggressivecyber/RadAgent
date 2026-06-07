"""Context Subgraph nodes — RAG retrieval, web search, evidence management.

Rules:
1. RAG first — real Ollama bge-m3 embedding + cosine similarity search
2. RAG insufficient → Web supplement
3. Both insufficient → block_no_context
4. Never use model built-in knowledge as sole source
5. All web results must have URLs
6. All evidence goes to evidence_map
7. Graceful degradation when Ollama unavailable
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir

from .doc_store import Geant4DocStore
from .rag_client import (
    DEFAULT_TOP_K,
    MIN_RELEVANCE_SCORE,
    OllamaEmbedder,
    RAGClient,
)
from .schemas import ContextSubgraphState

logger = logging.getLogger(__name__)

# Module-level singleton — index once, reuse across calls
_rag_client: RAGClient | None = None


def _get_rag_client() -> RAGClient:
    """Get or create the singleton RAG client with Geant4 docs indexed."""
    global _rag_client
    if _rag_client is not None:
        return _rag_client

    embedder = OllamaEmbedder()
    client = RAGClient(embedder=embedder)
    _rag_client = client
    return client


def reset_rag_client() -> None:
    """Reset the singleton RAG client (for testing)."""
    global _rag_client
    _rag_client = None


async def _ensure_indexed(client: RAGClient) -> bool:
    """Ensure Geant4 documents are indexed. Returns True if index is populated."""
    if client.index.size > 0:
        return True

    store = Geant4DocStore()
    docs = store.get_documents()
    if not docs:
        logger.warning("Geant4 doc store returned 0 documents")
        return False

    try:
        count = await client.index_documents(docs)
        logger.info("Indexed %d/%d Geant4 documents", count, len(docs))
        return count > 0
    except Exception as exc:
        logger.error("Failed to index Geant4 documents: %s", exc)
        return False


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
    """Retrieve context from Geant4 RAG (Ollama bge-m3 + cosine similarity).

    Real RAG pipeline:
      1. Ensure Geant4 documents are indexed (with embeddings)
      2. Embed user query via Ollama
      3. Search index via cosine similarity
      4. Score based on result quality and quantity
    """
    user_query = state.get("user_query", "")
    context_dir = _get_context_dir(state.get("job_id", "unknown"))
    context_dir.mkdir(parents=True, exist_ok=True)

    rag_context: list[dict[str, Any]] = []
    rag_report: dict[str, Any] = {
        "source": "geant4_rag",
        "engine": "ollama_bge_m3",
        "queries": [user_query],
        "doc_store_size": 0,
    }

    client = _get_rag_client()

    # Step 1: Check Ollama availability
    ollama_available = await client.embedder.is_available()
    rag_report["ollama_available"] = ollama_available

    if not ollama_available:
        rag_report["error"] = "Ollama service unavailable at localhost:11434"
        rag_report["score"] = 0.0
        rag_report["note"] = "Ollama unavailable — RAG retrieval skipped"

        _save_rag_files(context_dir, rag_context, rag_report)
        return {
            "rag_context": rag_context,
            "rag_score": 0.0,
            "rag_report": rag_report,
            "needs_web_supplement": True,
        }

    # Step 2: Ensure documents are indexed
    indexed = await _ensure_indexed(client)
    rag_report["doc_store_size"] = client.index.size

    if not indexed:
        rag_report["error"] = "Failed to index Geant4 documents"
        rag_report["score"] = 0.0
        _save_rag_files(context_dir, rag_context, rag_report)
        return {
            "rag_context": rag_context,
            "rag_score": 0.0,
            "rag_report": rag_report,
            "needs_web_supplement": True,
        }

    # Step 3: Generate refined queries from user query
    queries = _generate_search_queries(user_query)
    rag_report["queries"] = queries

    # Step 4: Search for each query and deduplicate
    seen_ids: set[str] = set()
    for query in queries:
        try:
            results = await client.search(
                query, top_k=DEFAULT_TOP_K, min_score=MIN_RELEVANCE_SCORE,
            )
            for r in results:
                if r.doc_id not in seen_ids:
                    seen_ids.add(r.doc_id)
                    rag_context.append({
                        "doc_id": r.doc_id,
                        "title": r.title,
                        "content": r.content,
                        "source": r.source,
                        "score": round(r.score, 4),
                    })
        except Exception as exc:
            logger.warning("RAG search failed for query '%s': %s", query, exc)

    # Sort by score descending
    rag_context.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    # Step 5: Score based on result quality
    score = _compute_rag_score(rag_context)
    rag_report["score"] = score
    rag_report["result_count"] = len(rag_context)
    rag_report["top_scores"] = [r.get("score", 0.0) for r in rag_context[:5]]

    needs_web = score < 0.5

    _save_rag_files(context_dir, rag_context, rag_report)

    return {
        "rag_context": rag_context,
        "rag_score": score,
        "rag_report": rag_report,
        "needs_web_supplement": needs_web,
    }


def _generate_search_queries(user_query: str) -> list[str]:
    """Generate refined search queries from user query.

    Uses the user query directly plus a simplified variant.
    """
    queries = [user_query]

    # Add a simplified keyword query
    keywords = user_query.lower()
    for filler in ("how to ", "what is ", "create a ", "define ", "show me ", "please "):
        keywords = keywords.replace(filler, "").strip()
    if keywords and keywords != user_query.lower():
        queries.append(keywords)

    return queries[:3]


def _compute_rag_score(rag_context: list[dict[str, Any]]) -> float:
    """Compute RAG sufficiency score from results.

    Scoring:
      - 0 results → 0.0
      - 1+ results with score >= 0.7 → up to 1.0
      - Results with lower scores → proportional
    """
    if not rag_context:
        return 0.0

    top_scores = [r.get("score", 0.0) for r in rag_context[:5]]
    max_score = max(top_scores) if top_scores else 0.0
    avg_score = sum(top_scores) / len(top_scores) if top_scores else 0.0

    # Weighted: 60% best result, 40% average of top-5
    raw_score = 0.6 * max_score + 0.4 * avg_score

    # Bonus for multiple high-quality results
    high_quality_count = sum(1 for s in top_scores if s >= 0.7)
    bonus = min(0.2, high_quality_count * 0.05)

    return min(1.0, raw_score + bonus)


def _save_rag_files(
    context_dir: Path,
    rag_context: list[dict[str, Any]],
    rag_report: dict[str, Any],
) -> None:
    """Save RAG context and report to disk."""
    (context_dir / "rag_context.json").write_text(
        json.dumps(rag_context, indent=2, ensure_ascii=False)
    )
    (context_dir / "rag_sufficiency.json").write_text(
        json.dumps(rag_report, indent=2, ensure_ascii=False)
    )


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
