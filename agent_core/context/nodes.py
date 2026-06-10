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

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from agent_core.workspace.io import get_job_dir, get_workspace_root
from agent_core.workspace.paths import STAGE_CONTEXT

from .doc_store import Geant4DocStore
from .rag_client import (
    DEFAULT_TOP_K,
    EMBED_MODEL,
    MIN_RELEVANCE_SCORE,
    OLLAMA_BASE_URL,
    OllamaEmbedder,
    RAGClient,
)
from .schemas import ContextSubgraphState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RAG coverage categories — required for complex Geant4 modelling
# ---------------------------------------------------------------------------

REQUIRED_RAG_CATEGORIES: dict[str, list[str]] = {
    "geometry": [
        "G4Box",
        "G4Tubs",
        "G4LogicalVolume",
        "G4PVPlacement",
        "solid",
        "logical volume",
        "physical volume",
        "geometry",
    ],
    "materials": [
        "G4Material",
        "G4NistManager",
        "density",
        "element",
        "material",
    ],
    "source": [
        "G4ParticleGun",
        "G4GeneralParticleSource",
        "GPS",
        "primary generator",
        "particle source",
    ],
    "physics": [
        "physics list",
        "FTFP_BERT",
        "QGSP",
        "electromagnetic",
        "hadronic",
    ],
    "scoring": [
        "sensitive detector",
        "G4VSensitiveDetector",
        "scorer",
        "dose",
        "edep",
        "energy deposition",
    ],
    "output": [
        "RunAction",
        "analysis manager",
        "CSV",
        "output",
        "file",
    ],
}

HARD_REQUIRED_CATEGORIES = {"geometry", "materials", "source", "scoring"}

# Concurrency lock for index building
_index_lock = asyncio.Lock()

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
    """Ensure Geant4 documents are indexed. Returns True if index is populated.

    Uses ``_index_lock`` to prevent concurrent jobs from building the
    index simultaneously.
    """
    if client.index.size > 0:
        return True

    async with _index_lock:
        # Double-check after acquiring lock
        if client.index.size > 0:
            return True

        store = Geant4DocStore()
        docs = store.get_documents()
        if not docs:
            logger.warning("Geant4 doc store returned 0 documents")
            return False

        try:
            sqlite_db = _geant4_sqlite_index_path()
            if sqlite_db.is_file() and client.load_sqlite_index(sqlite_db):
                supplemental = client.index.add_lexical_documents(docs)
                count = client.index.size
                logger.info(
                    "Loaded prebuilt Geant4 RAG SQLite index: %s; supplemental_docs=%d",
                    sqlite_db,
                    supplemental,
                )
            else:
                cache_path = _rag_index_cache_path(docs)
                count = await client.index_documents_cached(docs, cache_path)
            logger.info("Indexed %d/%d Geant4 documents", count, len(docs))
            return count > 0
        except Exception as exc:
            logger.error("Failed to index Geant4 documents: %s", exc)
            return False


def _geant4_sqlite_index_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "knowledge_base"
        / "geant4"
        / "data"
        / "geant4_index.db"
    )


def _rag_index_cache_path(docs: list[Any]) -> Path:
    """Return cache path keyed by doc content and embedding configuration."""
    fingerprint = hashlib.sha256()
    fingerprint.update(EMBED_MODEL.encode("utf-8"))
    fingerprint.update(str(OLLAMA_BASE_URL).encode("utf-8"))
    for doc in docs:
        fingerprint.update(doc.doc_id.encode("utf-8"))
        fingerprint.update(doc.title.encode("utf-8"))
        fingerprint.update(doc.content.encode("utf-8"))
        fingerprint.update(doc.source.encode("utf-8"))
    digest = fingerprint.hexdigest()[:16]
    return get_workspace_root() / ".cache" / "rag" / f"geant4_doc_index_{digest}.json"


def _get_context_dir(job_id: str) -> Path:
    """Return the context directory for a job."""
    return get_job_dir(job_id) / STAGE_CONTEXT


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
    ollama_available = await client.backend_available()
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
                query,
                top_k=DEFAULT_TOP_K,
                min_score=MIN_RELEVANCE_SCORE,
            )
            for r in results:
                if r.doc_id not in seen_ids:
                    seen_ids.add(r.doc_id)
                    rag_context.append(
                        {
                            "doc_id": r.doc_id,
                            "title": r.title,
                            "content": r.content,
                            "source": r.source,
                            "score": round(r.score, 4),
                        }
                    )
        except Exception as exc:
            logger.warning("RAG search failed for query '%s': %s", query, exc)

    # Sort by score descending
    rag_context.sort(key=lambda x: x.get("score", 0.0), reverse=True)

    # Step 5: Score based on result quality and coverage
    score, coverage_report = _compute_rag_score(rag_context)
    rag_report["score"] = score
    rag_report["coverage"] = coverage_report["coverage"]
    rag_report["missing_categories"] = coverage_report["missing_categories"]
    rag_report["missing_hard_required"] = coverage_report["missing_hard_required"]
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


def compute_rag_coverage(
    rag_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """Check whether RAG results cover all required Geant4 modelling categories."""
    combined_text = "\n".join(
        f"{item.get('title', '')}\n{item.get('content', '')}\n{item.get('snippet', '')}"
        for item in rag_context
    ).lower()

    coverage: dict[str, bool] = {}
    for category, keywords in REQUIRED_RAG_CATEGORIES.items():
        coverage[category] = any(keyword.lower() in combined_text for keyword in keywords)

    missing_categories = sorted(cat for cat, covered in coverage.items() if not covered)
    missing_hard_required = sorted(
        cat for cat in HARD_REQUIRED_CATEGORIES if not coverage.get(cat, False)
    )

    return {
        "coverage": coverage,
        "covered_count": sum(1 for v in coverage.values() if v),
        "missing_categories": missing_categories,
        "missing_hard_required": missing_hard_required,
    }


def _compute_rag_score(
    rag_context: list[dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    """Compute RAG sufficiency score — similarity + coverage.

    Returns (score, coverage_report).  Hard-required categories missing
    caps the score at 0.49 so ``allow_rag`` is never granted.
    """
    if not rag_context:
        return 0.0, {
            "coverage": {},
            "covered_count": 0,
            "missing_categories": list(REQUIRED_RAG_CATEGORIES),
            "missing_hard_required": list(HARD_REQUIRED_CATEGORIES),
        }

    top_scores = [float(r.get("score", 0.0)) for r in rag_context[:5]]
    avg_score = sum(top_scores) / len(top_scores) if top_scores else 0.0
    max_score = max(top_scores) if top_scores else 0.0

    coverage_report = compute_rag_coverage(rag_context)
    covered_count = int(coverage_report["covered_count"])
    coverage_score = covered_count / len(REQUIRED_RAG_CATEGORIES)

    score = 0.45 * max_score + 0.25 * avg_score + 0.30 * coverage_score

    if coverage_report["missing_hard_required"]:
        score = min(score, 0.49)

    return round(min(1.0, score), 4), coverage_report


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
    """Score RAG context sufficiency.

    ``allow_rag`` is only granted when score >= 0.7 **and** no
    hard-required categories are missing.
    """
    score = float(state.get("rag_score", 0.0))
    rag_report = state.get("rag_report", {})
    missing_hard = rag_report.get("missing_hard_required", [])

    if score >= 0.7 and not missing_hard:
        return {
            "context_decision": "allow_rag",
            "needs_web_supplement": False,
        }

    return {
        "context_decision": "needs_web",
        "needs_web_supplement": True,
    }


# ---------------------------------------------------------------------------
# Web quality gate (Phase 3)
# ---------------------------------------------------------------------------

TRUSTED_WEB_DOMAINS = [
    "geant4.web.cern.ch",
    "cern.ch",
    "github.com/Geant4",
    "geant4-userdoc.web.cern.ch",
]

WEB_KEYWORDS = [
    "Geant4",
    "G4Material",
    "G4PVPlacement",
    "G4ParticleGun",
    "G4GeneralParticleSource",
    "G4VSensitiveDetector",
    "dose",
    "energy deposition",
    "physics list",
]


def score_web_quality(
    web_context: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate web search result quality.

    Requires:
      - At least 2 items with valid URLs
      - At least 1 from a trusted domain
      - At least 2 with Geant4 keyword hits
    """
    valid_items: list[dict[str, Any]] = []
    trusted_items: list[dict[str, Any]] = []
    keyword_items: list[dict[str, Any]] = []

    for item in web_context:
        url = str(item.get("url", ""))
        if not url.startswith(("http://", "https://")):
            continue

        valid_items.append(item)

        if any(domain in url for domain in TRUSTED_WEB_DOMAINS):
            trusted_items.append(item)

        text = (
            str(item.get("title", ""))
            + " "
            + str(item.get("snippet", ""))
            + " "
            + str(item.get("content", ""))
        ).lower()

        if any(keyword.lower() in text for keyword in WEB_KEYWORDS):
            keyword_items.append(item)

    sufficient = len(valid_items) >= 2 and len(trusted_items) >= 1 and len(keyword_items) >= 2

    return {
        "sufficient": sufficient,
        "valid_url_count": len(valid_items),
        "trusted_source_count": len(trusted_items),
        "keyword_hit_count": len(keyword_items),
        "trusted_urls": [i.get("url", "") for i in trusted_items],
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
    """Score combined RAG + Web context and make final decision.

    Decision logic:
      - RAG sufficient (score >= 0.7, no hard-required missing) → allow_rag
      - Web quality sufficient → allow_with_web_supplement
      - Otherwise → block_no_context
    """
    rag_score = float(state.get("rag_score", 0.0))
    rag_report = state.get("rag_report", {})
    missing_hard = rag_report.get("missing_hard_required", [])

    web_context = state.get("web_context", [])
    web_quality = score_web_quality(web_context)

    if rag_score >= 0.7 and not missing_hard:
        decision = "allow_rag"
    elif web_quality["sufficient"]:
        decision = "allow_with_web_supplement"
    else:
        decision = "block_no_context"

    report = {
        "rag_score": rag_score,
        "rag_missing_hard_required": missing_hard,
        "web_quality": web_quality,
        "decision": decision,
    }

    context_dir = _get_context_dir(state.get("job_id", "unknown"))
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
