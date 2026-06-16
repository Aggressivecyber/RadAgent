"""Geant4 documentation search tool backend."""

from __future__ import annotations

from typing import Any

_GEANT4_RAG_CLIENT = None


def get_geant4_rag_client():
    global _GEANT4_RAG_CLIENT
    if _GEANT4_RAG_CLIENT is None:
        from agent_core.context.nodes import _get_rag_client

        _GEANT4_RAG_CLIENT = _get_rag_client()
    return _GEANT4_RAG_CLIENT


async def search_geant4_docs(query: str, *, top_k: int = 5) -> dict[str, Any]:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return {"ok": False, "error": "query must be non-empty."}

    client = get_geant4_rag_client()
    try:
        if not await client.backend_available():
            return {"ok": False, "error": "Geant4 RAG backend unavailable."}
        if not client.index_ready():
            try:
                from agent_core.context.nodes import _ensure_indexed

                await _ensure_indexed(client)
            except Exception:
                return {"ok": False, "error": "Geant4 RAG index unavailable."}
        if not client.index_ready():
            return {"ok": False, "error": "Geant4 RAG index unavailable."}
        results = await client.search(
            normalized_query,
            top_k=max(1, min(int(top_k or 5), 10)),
            min_score=0.0,
        )
    except Exception as exc:
        return {"ok": False, "error": f"Geant4 RAG search failed: {exc}"}

    return {
        "ok": True,
        "query": normalized_query,
        "results": [
            {
                "doc_id": result.doc_id,
                "title": result.title,
                "content": result.content,
                "source": result.source,
                "score": round(float(result.score), 4),
            }
            for result in results
        ],
    }
