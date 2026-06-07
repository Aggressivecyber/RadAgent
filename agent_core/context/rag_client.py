"""RAG client — Ollama bge-m3 embedding + cosine similarity search.

Architecture:
  1. Embed query via Ollama POST /api/embed (bge-m3, 1024-dim)
  2. Search document index via cosine similarity
  3. Return ranked results with scores

Rules:
  - All network calls have timeouts
  - Graceful fallback when Ollama unavailable (returns empty)
  - Pure functions for similarity computation (numpy)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# --- Configuration ---

OLLAMA_BASE_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
EMBED_TIMEOUT_S = 60.0
DEFAULT_TOP_K = 5
MIN_RELEVANCE_SCORE = 0.3


@dataclass(frozen=True)
class RAGDocument:
    """A single document in the RAG index."""

    doc_id: str
    title: str
    content: str
    source: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RAGResult:
    """A single search result from RAG retrieval."""

    doc_id: str
    title: str
    content: str
    source: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


def cosine_similarity(query_vec: NDArray[np.floating[Any]], doc_vecs: NDArray[np.floating[Any]]) -> NDArray[np.floating[Any]]:
    """Compute cosine similarity between query and document vectors.

    Args:
        query_vec: shape (dim,)
        doc_vecs: shape (n_docs, dim)

    Returns:
        shape (n_docs,) similarity scores
    """
    if doc_vecs.size == 0:
        return np.array([], dtype=np.float64)

    query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
    doc_norms = doc_vecs / (np.linalg.norm(doc_vecs, axis=1, keepdims=True) + 1e-10)
    return (doc_norms @ query_norm).astype(np.float64)


class OllamaEmbedder:
    """Embed text using Ollama bge-m3."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = EMBED_MODEL,
        timeout: float = EMBED_TIMEOUT_S,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def embed(self, text: str) -> NDArray[np.floating[Any]] | None:
        """Embed a single text string. Returns None on failure."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self._model, "input": text},
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                if embeddings and len(embeddings) > 0:
                    return np.array(embeddings[0], dtype=np.float64)
                return None
        except Exception as exc:
            logger.warning("Ollama embed failed: %s", exc)
            return None

    async def embed_batch(self, texts: list[str]) -> list[NDArray[np.floating[Any]] | None]:
        """Embed multiple texts. Falls back to sequential if batch fails."""
        # Try batch first
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self._model, "input": texts},
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = data.get("embeddings", [])
                results: list[NDArray[np.floating[Any]] | None] = []
                for emb in embeddings:
                    if emb:
                        results.append(np.array(emb, dtype=np.float64))
                    else:
                        results.append(None)
                # Pad if Ollama returned fewer than requested
                while len(results) < len(texts):
                    results.append(None)
                return results
        except Exception as exc:
            logger.warning("Ollama batch embed failed (%s), falling back to sequential", exc)

        # Fallback: embed one-by-one
        results: list[NDArray[np.floating[Any]] | None] = []
        for text in texts:
            emb = await self.embed(text)
            results.append(emb)
        return results

    async def is_available(self) -> bool:
        """Check if Ollama service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


class DocumentIndex:
    """In-memory document index with pre-computed embeddings."""

    def __init__(self) -> None:
        self._documents: list[RAGDocument] = []
        self._embeddings: NDArray[np.floating[Any]] = np.array([], dtype=np.float64)

    @property
    def size(self) -> int:
        return len(self._documents)

    @property
    def documents(self) -> list[RAGDocument]:
        return list(self._documents)

    def add_documents(
        self,
        documents: list[RAGDocument],
        embeddings: list[NDArray[np.floating[Any]] | None],
    ) -> None:
        """Add documents with their pre-computed embeddings.

        Only adds documents where embedding is not None.
        """
        valid_docs: list[RAGDocument] = []
        valid_embs: list[NDArray[np.floating[Any]]] = []

        for doc, emb in zip(documents, embeddings):
            if emb is not None:
                valid_docs.append(doc)
                valid_embs.append(emb)

        if not valid_docs:
            return

        new_embs = np.stack(valid_embs)
        if self._embeddings.size == 0:
            self._embeddings = new_embs
        else:
            self._embeddings = np.vstack([self._embeddings, new_embs])
        self._documents.extend(valid_docs)

    def search(
        self,
        query_embedding: NDArray[np.floating[Any]],
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_RELEVANCE_SCORE,
    ) -> list[RAGResult]:
        """Search the index using cosine similarity.

        Args:
            query_embedding: Query vector (dim,)
            top_k: Maximum results to return
            min_score: Minimum cosine similarity threshold

        Returns:
            List of RAGResult sorted by score descending
        """
        if self._embeddings.size == 0 or len(self._documents) == 0:
            return []

        scores = cosine_similarity(query_embedding, self._embeddings)

        # Filter by minimum score and sort
        indices_above_threshold = np.where(scores >= min_score)[0]
        sorted_indices = indices_above_threshold[np.argsort(-scores[indices_above_threshold])]

        results: list[RAGResult] = []
        for idx in sorted_indices[:top_k]:
            doc = self._documents[int(idx)]
            results.append(
                RAGResult(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    content=doc.content,
                    source=doc.source,
                    score=float(scores[idx]),
                    metadata=doc.metadata,
                )
            )
        return results


class RAGClient:
    """High-level RAG client: embed query → search index → return results."""

    def __init__(
        self,
        embedder: OllamaEmbedder | None = None,
        index: DocumentIndex | None = None,
    ) -> None:
        self._embedder = embedder or OllamaEmbedder()
        self._index = index or DocumentIndex()

    @property
    def embedder(self) -> OllamaEmbedder:
        return self._embedder

    @property
    def index(self) -> DocumentIndex:
        return self._index

    async def is_available(self) -> bool:
        """Check if the RAG system is usable (Ollama reachable + index populated)."""
        ollama_ok = await self._embedder.is_available()
        return ollama_ok and self._index.size > 0

    async def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_RELEVANCE_SCORE,
    ) -> list[RAGResult]:
        """Search the document index for relevant documents.

        Args:
            query: Natural language query
            top_k: Maximum results to return
            min_score: Minimum relevance threshold

        Returns:
            Ranked search results
        """
        query_embedding = await self._embedder.embed(query)
        if query_embedding is None:
            logger.warning("Failed to embed query, returning empty results")
            return []

        return self._index.search(query_embedding, top_k=top_k, min_score=min_score)

    async def index_documents(self, documents: list[RAGDocument]) -> int:
        """Add documents to the index with auto-embedding.

        Returns:
            Number of documents successfully indexed
        """
        texts = [f"{doc.title} {doc.content}" for doc in documents]
        embeddings = await self._embedder.embed_batch(texts)
        self._index.add_documents(documents, embeddings)
        return sum(1 for e in embeddings if e is not None)
