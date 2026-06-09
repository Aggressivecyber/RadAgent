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

import json
import logging
import os
import pickle
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

# --- Configuration (environment-variable driven) ---

OLLAMA_BASE_URL = os.getenv("RADAGENT_OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("RADAGENT_EMBED_MODEL", "bge-m3")
EMBED_TIMEOUT_S = float(os.getenv("RADAGENT_EMBED_TIMEOUT_S", "60"))
DEFAULT_TOP_K = 5
MIN_RELEVANCE_SCORE = 0.3
LEXICAL_ONLY_MIN_SCORE = 0.05
CONTENT_WINDOW_CHARS = 3600


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


Vec = NDArray[np.floating[Any]]


def cosine_similarity(query_vec: Vec, doc_vecs: Vec) -> Vec:
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
    result: Vec = (doc_norms @ query_norm).astype(np.float64)
    return result


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
                    arr: NDArray[np.floating[Any]] = np.array(
                        embeddings[0],
                        dtype=np.float64,
                    )
                    return arr
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
        fallback: list[NDArray[np.floating[Any]] | None] = []
        for text in texts:
            emb = await self.embed(text)
            fallback.append(emb)
        return fallback

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

    @property
    def embedding_dim(self) -> int | None:
        if self._embeddings.size == 0:
            return None
        return int(self._embeddings.shape[1])

    def add_documents(
        self,
        documents: list[RAGDocument],
        embeddings: list[NDArray[np.floating[Any]] | None],
    ) -> None:
        """Add documents with their pre-computed embeddings.

        Only adds documents where embedding is not None.

        Raises:
            ValueError: If embedding dimensions are inconsistent or
                mismatch with existing index.
        """
        valid_docs: list[RAGDocument] = []
        valid_embs: list[NDArray[np.floating[Any]]] = []

        for doc, emb in zip(documents, embeddings):
            if emb is None:
                continue
            if emb.ndim != 1:
                raise ValueError(f"Embedding must be 1-D, got shape {emb.shape}")
            valid_docs.append(doc)
            valid_embs.append(emb)

        if not valid_docs:
            return

        dims = {int(emb.shape[0]) for emb in valid_embs}
        if len(dims) != 1:
            raise ValueError(f"Inconsistent embedding dimensions: {sorted(dims)}")

        new_dim = next(iter(dims))

        if self._embeddings.size != 0:
            existing_dim = int(self._embeddings.shape[1])
            if existing_dim != new_dim:
                raise ValueError(
                    f"Embedding dimension mismatch: existing={existing_dim}, new={new_dim}"
                )

        new_embs = np.stack(valid_embs)
        if self._embeddings.size == 0:
            self._embeddings = new_embs
        else:
            self._embeddings = np.vstack([self._embeddings, new_embs])
        self._documents.extend(valid_docs)

    def replace_documents(
        self,
        documents: list[RAGDocument],
        embeddings: list[NDArray[np.floating[Any]]],
    ) -> None:
        """Replace index contents with validated documents and embeddings."""
        self._documents = []
        self._embeddings = np.array([], dtype=np.float64)
        self.add_documents(documents, embeddings)

    def add_lexical_documents(self, documents: list[RAGDocument]) -> int:
        """Add supplemental docs with zero embeddings for lexical reranking."""
        if not documents:
            return 0
        dim = self.embedding_dim
        if dim is None:
            return 0
        existing_ids = {doc.doc_id for doc in self._documents}
        new_docs = [doc for doc in documents if doc.doc_id not in existing_ids]
        if not new_docs:
            return 0
        zero_embeddings = [np.zeros(dim, dtype=np.float64) for _ in new_docs]
        self.add_documents(new_docs, zero_embeddings)
        return len(new_docs)

    def save(self, path: Path) -> None:
        """Persist the in-memory index to disk as JSON."""
        if self._embeddings.size == 0:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "documents": [
                {
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "content": doc.content,
                    "source": doc.source,
                    "metadata": doc.metadata,
                }
                for doc in self._documents
            ],
            "embeddings": self._embeddings.tolist(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def load(self, path: Path) -> bool:
        """Load a persisted index. Returns False if cache is unusable."""
        if not path.is_file():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            docs_payload = payload.get("documents", [])
            embeddings_payload = payload.get("embeddings", [])
            if not isinstance(docs_payload, list) or not isinstance(embeddings_payload, list):
                return False
            if len(docs_payload) != len(embeddings_payload):
                return False
            documents = [
                RAGDocument(
                    doc_id=str(item["doc_id"]),
                    title=str(item["title"]),
                    content=str(item["content"]),
                    source=str(item["source"]),
                    metadata=dict(item.get("metadata", {})),
                )
                for item in docs_payload
                if isinstance(item, dict)
            ]
            embeddings = [
                np.array(embedding, dtype=np.float64)
                for embedding in embeddings_payload
                if isinstance(embedding, list)
            ]
            if len(documents) != len(embeddings):
                return False
            self.replace_documents(documents, embeddings)
            return self.size > 0
        except Exception as exc:
            logger.warning("Failed to load RAG index cache %s: %s", path, exc)
            return False

    def load_sqlite(self, db_path: Path) -> bool:
        """Load a prebuilt SQLite RAG index with pickled numpy embeddings."""
        if not db_path.is_file():
            return False
        documents: list[RAGDocument] = []
        embeddings: list[NDArray[np.floating[Any]]] = []
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                rows = conn.execute(
                    "SELECT id, source, title, content, embedding, metadata FROM documents"
                ).fetchall()
            finally:
                conn.close()

            for doc_id, source, title, content, emb_blob, metadata_json in rows:
                if not emb_blob:
                    continue
                try:
                    embedding = np.asarray(pickle.loads(emb_blob), dtype=np.float64)
                    metadata = json.loads(metadata_json) if metadata_json else {}
                except Exception:
                    continue
                if embedding.ndim != 1:
                    continue
                documents.append(
                    RAGDocument(
                        doc_id=f"sqlite:{doc_id}",
                        title=str(title or ""),
                        content=str(content or ""),
                        source=str(source or "geant4_sqlite"),
                        metadata=metadata if isinstance(metadata, dict) else {},
                    )
                )
                embeddings.append(embedding)

            if not documents:
                return False
            self.replace_documents(documents, embeddings)
            logger.info("Loaded SQLite RAG index %s (%d docs)", db_path, self.size)
            return True
        except Exception as exc:
            logger.warning("Failed to load SQLite RAG index %s: %s", db_path, exc)
            return False

    def search(
        self,
        query_embedding: NDArray[np.floating[Any]] | None,
        top_k: int = DEFAULT_TOP_K,
        min_score: float = MIN_RELEVANCE_SCORE,
        query_text: str = "",
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

        if query_embedding is None:
            semantic_scores = np.zeros(len(self._documents), dtype=np.float64)
            min_score = min(min_score, LEXICAL_ONLY_MIN_SCORE)
        else:
            semantic_scores = cosine_similarity(query_embedding, self._embeddings)

        lexical_scores = (
            self._lexical_scores(query_text)
            if query_text.strip()
            else np.zeros_like(semantic_scores)
        )

        # Keep semantic recall useful, but make exact Geant4 API/file/macro
        # mentions strong enough to pull the relevant manual chunk to the top.
        scores = (0.75 * semantic_scores) + (1.60 * lexical_scores)

        # Filter by minimum score and sort
        indices_above_threshold = np.where(scores >= min_score)[0]
        sorted_indices = indices_above_threshold[np.argsort(-scores[indices_above_threshold])]

        results: list[RAGResult] = []
        for idx in sorted_indices[:top_k]:
            doc = self._documents[int(idx)]
            content, expanded_ids = self._expanded_content(int(idx), lexical_scores)
            results.append(
                RAGResult(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    content=content,
                    source=doc.source,
                    score=float(scores[idx]),
                    metadata={
                        **doc.metadata,
                        "semantic_score": float(semantic_scores[idx]),
                        "lexical_score": float(lexical_scores[idx])
                        if lexical_scores.size
                        else 0.0,
                        "expanded_doc_ids": expanded_ids,
                    },
                )
            )
        return results

    def _lexical_scores(self, query_text: str) -> NDArray[np.floating[Any]]:
        terms = _query_terms(query_text)
        if not terms.exact and not terms.keyword:
            return np.zeros(len(self._documents), dtype=np.float64)
        scores = np.zeros(len(self._documents), dtype=np.float64)
        for idx, doc in enumerate(self._documents):
            title = doc.title.lower()
            content = doc.content.lower()
            source = doc.source.lower()
            path = str(doc.metadata.get("path", "")).lower()
            haystack = f"{title}\n{source}\n{path}\n{content}"
            score = 0.0
            exact_hits = 0
            for term in terms.exact:
                term_score = 0.0
                if term in title:
                    term_score += 8.0
                if term in path:
                    term_score += 4.0
                if term in content:
                    term_score += 5.0
                if term_score > 0.0:
                    exact_hits += 1
                    score += term_score

            keyword_score = 0.0
            for term in terms.keyword:
                if term in title:
                    keyword_score += 1.0
                if term in content:
                    keyword_score += 0.25
            score += min(keyword_score, 3.0)

            if terms.exact:
                score += 4.0 * (exact_hits / len(terms.exact))
                if exact_hits >= min(2, len(terms.exact)):
                    score += 2.0
                if exact_hits > 0 and _is_manual_document(doc):
                    score += 3.0

            phrase = _compact_query_phrase(query_text)
            if phrase and phrase in haystack:
                score += 3.0

            # Curated RadAgent/Geant4 repair docs are intentionally small and
            # should win only when they actually match concrete exact terms.
            if exact_hits > 0 and not doc.doc_id.startswith("sqlite:"):
                score += 2.0
            scores[idx] = score
        max_score = float(scores.max()) if scores.size else 0.0
        if max_score <= 0.0:
            return scores
        return scores / max_score

    def _expanded_content(
        self,
        idx: int,
        lexical_scores: NDArray[np.floating[Any]],
    ) -> tuple[str, list[str]]:
        """Return current chunk plus adjacent manual chunks for strong lexical hits."""
        doc = self._documents[idx]
        if lexical_scores.size == 0 or lexical_scores[idx] < 0.55:
            return doc.content, []

        indices = [idx]
        for neighbor_idx in (idx - 1, idx + 1):
            if 0 <= neighbor_idx < len(self._documents) and self._same_chunk_group(
                doc,
                self._documents[neighbor_idx],
            ):
                indices.append(neighbor_idx)
        indices = sorted(set(indices))

        parts: list[str] = []
        expanded_ids: list[str] = []
        total = 0
        for part_idx in indices:
            part_doc = self._documents[part_idx]
            text = part_doc.content.strip()
            if not text:
                continue
            if total + len(text) > CONTENT_WINDOW_CHARS and parts:
                break
            parts.append(text)
            expanded_ids.append(part_doc.doc_id)
            total += len(text)
        if not parts:
            return doc.content, []
        return "\n\n--- adjacent manual chunk ---\n\n".join(parts), expanded_ids

    @staticmethod
    def _same_chunk_group(left: RAGDocument, right: RAGDocument) -> bool:
        left_path = left.metadata.get("path")
        right_path = right.metadata.get("path")
        if left_path or right_path:
            return (
                left.source == right.source
                and left.title == right.title
                and left_path == right_path
            )
        return left.source == right.source and left.title == right.title


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

    async def backend_available(self) -> bool:
        """Check if the Ollama backend is reachable."""
        return await self._embedder.is_available()

    def index_ready(self) -> bool:
        """Check if the document index is populated."""
        return self._index.size > 0

    async def is_available(self) -> bool:
        """Check if the RAG system is usable (Ollama reachable + index populated)."""
        return await self.backend_available() and self.index_ready()

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
            logger.warning("Failed to embed query, falling back to lexical RAG search")

        return self._index.search(
            query_embedding,
            top_k=top_k,
            min_score=min_score,
            query_text=query,
        )

    async def index_documents(self, documents: list[RAGDocument]) -> int:
        """Add documents to the index with auto-embedding.

        Returns:
            Number of documents successfully indexed
        """
        texts = [f"{doc.title} {doc.content}" for doc in documents]
        embeddings = await self._embedder.embed_batch(texts)
        self._index.add_documents(documents, embeddings)
        return sum(1 for e in embeddings if e is not None)

    async def index_documents_cached(
        self,
        documents: list[RAGDocument],
        cache_path: Path,
    ) -> int:
        """Load a cached index when valid, otherwise embed and persist it."""
        if self._index.load(cache_path):
            logger.info("Loaded RAG index cache: %s (%d docs)", cache_path, self._index.size)
            return self._index.size
        count = await self.index_documents(documents)
        if count > 0:
            self._index.save(cache_path)
        return count

    def load_sqlite_index(self, db_path: Path) -> bool:
        """Load a prebuilt SQLite vector index into this client."""
        return self._index.load_sqlite(db_path)


@dataclass(frozen=True)
class QueryTerms:
    exact: list[str]
    keyword: list[str]


def _query_terms(query_text: str) -> QueryTerms:
    """Extract exact API/file terms separately from broad keywords."""
    exact_terms: list[str] = []
    keyword_terms: list[str] = []
    term_pattern = (
        r"/[A-Za-z0-9_./-]+|"
        r"[A-Za-z0-9_./-]+\.(?:hh|cc|cpp|h|hpp|mac|json|csv)|"
        r"G4[A-Za-z0-9_:<>]+|"
        r"[A-Z][A-Za-z0-9_]*[A-Z_][A-Za-z0-9_]*|"
        r"[A-Za-z_][A-Za-z0-9_]{4,}"
    )
    for token in re.findall(term_pattern, query_text):
        token = token.rstrip(".,;:)")
        lowered = token.lower()
        if lowered in {
            "geant4",
            "repair",
            "module",
            "generated",
            "files",
            "include",
            "source",
            "using",
            "should",
            "must",
        }:
            continue
        if _is_exact_rag_term(token):
            exact_terms.append(lowered)
        else:
            keyword_terms.append(lowered)
    exact = sorted(set(exact_terms), key=len, reverse=True)[:24]
    keyword = sorted(set(keyword_terms), key=len, reverse=True)[:24]
    return QueryTerms(exact=exact, keyword=keyword)


def _is_exact_rag_term(token: str) -> bool:
    if token.startswith("/"):
        return True
    if re.match(r"G4[A-Za-z0-9_:<>]+$", token):
        return True
    if re.search(r"\.(?:hh|cc|cpp|h|hpp|mac|json|csv)$", token, re.IGNORECASE):
        return True
    if "_" in token:
        return True
    return bool(re.search(r"[a-z][A-Z]|[A-Z]{2,}", token))


def _compact_query_phrase(query_text: str) -> str:
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z0-9_./:-]+", query_text)
        if len(word) >= 3
    ]
    if len(words) < 3:
        return ""
    return " ".join(words[:8])


def _is_manual_document(doc: RAGDocument) -> bool:
    source = doc.source.lower()
    title = doc.title.lower()
    path = str(doc.metadata.get("path", "")).lower()
    return (
        source in {"appdev", "toolkit", "geant4_reference"}
        or "documentation" in title
        or path.endswith(".html")
    )
