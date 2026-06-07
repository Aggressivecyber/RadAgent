"""Tests for Context RAG — real Ollama bge-m3 integration.

Verifies:
  - RAGClient cosine similarity correctness
  - DocumentIndex search returns ranked results
  - OllamaEmbedder graceful failure on bad endpoint
  - Geant4DocStore has correct document structure
  - retrieve_rag_context produces real results (or graceful degradation)
  - _compute_rag_score scoring logic
  - _generate_search_queries query expansion
  - retrieve_rag_context falls back when Ollama unavailable
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from agent_core.context.doc_store import Geant4DocStore
from agent_core.context.nodes import (
    _compute_rag_score,
    _generate_search_queries,
    retrieve_rag_context,
    reset_rag_client,
)
from agent_core.context.rag_client import (
    DocumentIndex,
    OllamaEmbedder,
    RAGClient,
    RAGDocument,
    cosine_similarity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc(doc_id: str, title: str, content: str) -> RAGDocument:
    return RAGDocument(doc_id=doc_id, title=title, content=content, source="test")


def _unit_vec(dim: int, idx: int) -> np.ndarray:
    """Create a unit vector with 1 at position idx."""
    v = np.zeros(dim, dtype=np.float64)
    v[idx] = 1.0
    return v


# ---------------------------------------------------------------------------
# cosine_similarity tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = np.array([1.0, 2.0, 3.0])
        result = cosine_similarity(v, v.reshape(1, -1))
        assert abs(result[0] - 1.0) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        q = np.array([1.0, 0.0])
        docs = np.array([[0.0, 1.0], [1.0, 0.0]])
        result = cosine_similarity(q, docs)
        assert abs(result[0]) < 1e-6  # orthogonal
        assert abs(result[1] - 1.0) < 1e-6  # identical

    def test_empty_doc_matrix(self) -> None:
        q = np.array([1.0, 2.0])
        docs = np.array([], dtype=np.float64)
        result = cosine_similarity(q, docs)
        assert len(result) == 0

    def test_opposite_direction(self) -> None:
        v = np.array([1.0, 0.0, 0.0])
        opp = np.array([-1.0, 0.0, 0.0])
        result = cosine_similarity(v, opp.reshape(1, -1))
        assert abs(result[0] + 1.0) < 1e-6  # cosine = -1


# ---------------------------------------------------------------------------
# DocumentIndex tests
# ---------------------------------------------------------------------------


class TestDocumentIndex:
    def test_empty_index_returns_empty(self) -> None:
        idx = DocumentIndex()
        query = np.array([1.0, 0.0])
        assert idx.search(query) == []
        assert idx.size == 0

    def test_add_and_search(self) -> None:
        idx = DocumentIndex()
        docs = [
            _make_doc("d1", "Geometry", "G4Box box solid"),
            _make_doc("d2", "Material", "G4NistManager materials"),
        ]
        embeddings = [
            np.array([1.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
        ]
        idx.add_documents(docs, embeddings)
        assert idx.size == 2

        # Query matching d1
        query = np.array([0.9, 0.1, 0.0])
        results = idx.search(query, top_k=2, min_score=0.3)
        assert len(results) >= 1
        assert results[0].doc_id == "d1"
        assert results[0].score > results[1].score if len(results) > 1 else True

    def test_min_score_filter(self) -> None:
        idx = DocumentIndex()
        docs = [_make_doc("d1", "X", "Y")]
        embeddings = [np.array([1.0, 0.0])]
        idx.add_documents(docs, embeddings)

        query = np.array([0.0, 1.0])  # orthogonal → score ~0
        results = idx.search(query, min_score=0.9)
        assert len(results) == 0

    def test_none_embedding_skipped(self) -> None:
        idx = DocumentIndex()
        docs = [
            _make_doc("d1", "A", "a"),
            _make_doc("d2", "B", "b"),
        ]
        embeddings: list[np.ndarray | None] = [
            np.array([1.0, 0.0]),
            None,  # Failed embedding
        ]
        idx.add_documents(docs, embeddings)
        assert idx.size == 1
        assert idx.documents[0].doc_id == "d1"

    def test_top_k_limits_results(self) -> None:
        idx = DocumentIndex()
        docs = [_make_doc(f"d{i}", f"T{i}", f"C{i}") for i in range(10)]
        # All embeddings point same direction
        embeddings = [np.array([1.0, 0.0]) for _ in range(10)]
        idx.add_documents(docs, embeddings)

        query = np.array([1.0, 0.0])
        results = idx.search(query, top_k=3)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# RAGClient tests
# ---------------------------------------------------------------------------


class TestRAGClient:
    async def test_search_with_mock_embedder(self) -> None:
        """RAGClient.search should return ranked results from index."""
        embedder = AsyncMock(spec=OllamaEmbedder)
        embedder.embed = AsyncMock(return_value=np.array([1.0, 0.0]))

        idx = DocumentIndex()
        docs = [
            _make_doc("d1", "Geant4 Box", "G4Box box geometry"),
            _make_doc("d2", "Material", "NIST material database"),
        ]
        doc_embs = [np.array([0.9, 0.1]), np.array([0.1, 0.9])]
        idx.add_documents(docs, doc_embs)

        client = RAGClient(embedder=embedder, index=idx)
        results = await client.search("box geometry")
        assert len(results) >= 1
        assert results[0].doc_id == "d1"  # Matches query direction
        embedder.embed.assert_called_once_with("box geometry")

    async def test_search_returns_empty_on_embed_failure(self) -> None:
        embedder = AsyncMock(spec=OllamaEmbedder)
        embedder.embed = AsyncMock(return_value=None)

        idx = DocumentIndex()
        client = RAGClient(embedder=embedder, index=idx)
        results = await client.search("test")
        assert results == []

    async def test_index_documents(self) -> None:
        embedder = AsyncMock(spec=OllamaEmbedder)
        embedder.embed_batch = AsyncMock(return_value=[
            np.array([1.0, 0.0]),
            np.array([0.0, 1.0]),
        ])

        idx = DocumentIndex()
        client = RAGClient(embedder=embedder, index=idx)
        docs = [_make_doc("d1", "A", "a"), _make_doc("d2", "B", "b")]
        count = await client.index_documents(docs)
        assert count == 2
        assert idx.size == 2

    async def test_is_available_checks_ollama_and_index(self) -> None:
        embedder = AsyncMock(spec=OllamaEmbedder)
        embedder.is_available = AsyncMock(return_value=True)

        idx = DocumentIndex()
        client = RAGClient(embedder=embedder, index=idx)

        # Empty index → not available
        assert await client.is_available() is False

        # Add a doc
        idx.add_documents([_make_doc("d1", "A", "a")], [np.array([1.0])])
        assert await client.is_available() is True


# ---------------------------------------------------------------------------
# OllamaEmbedder tests (unit, no real network)
# ---------------------------------------------------------------------------


class TestOllamaEmbedder:
    async def test_embed_returns_none_on_connection_error(self) -> None:
        embedder = OllamaEmbedder(base_url="http://localhost:19999")
        result = await embedder.embed("test")
        assert result is None

    async def test_is_available_returns_false_on_bad_port(self) -> None:
        embedder = OllamaEmbedder(base_url="http://localhost:19999")
        assert await embedder.is_available() is False

    async def test_embed_batch_returns_nones_on_failure(self) -> None:
        embedder = OllamaEmbedder(base_url="http://localhost:19999")
        results = await embedder.embed_batch(["a", "b"])
        assert results == [None, None]


# ---------------------------------------------------------------------------
# Geant4DocStore tests
# ---------------------------------------------------------------------------


class TestGeant4DocStore:
    def test_get_documents_returns_list(self) -> None:
        store = Geant4DocStore()
        docs = store.get_documents()
        assert isinstance(docs, list)
        assert len(docs) > 0

    def test_documents_have_required_fields(self) -> None:
        store = Geant4DocStore()
        docs = store.get_documents()
        for doc in docs:
            assert doc.doc_id, "doc_id must be non-empty"
            assert doc.title, "title must be non-empty"
            assert doc.content, "content must be non-empty"
            assert doc.source == "geant4_reference"

    def test_document_ids_are_unique(self) -> None:
        store = Geant4DocStore()
        docs = store.get_documents()
        ids = [d.doc_id for d in docs]
        assert len(ids) == len(set(ids)), "All doc_ids must be unique"

    def test_document_count_matches(self) -> None:
        store = Geant4DocStore()
        assert store.get_document_count() == len(store.get_documents())

    def test_documents_cover_key_topics(self) -> None:
        store = Geant4DocStore()
        docs = store.get_documents()
        titles = " ".join(d.title + " " + d.content for d in docs).lower()
        # Must cover key Geant4 concepts
        for keyword in ("g4box", "g4tubs", "g4material", "g4vsensitivedetector",
                        "g4particlegun", "g4runmanager", "processhits"):
            assert keyword in titles, f"Doc store must cover '{keyword}'"


# ---------------------------------------------------------------------------
# _compute_rag_score tests
# ---------------------------------------------------------------------------


class TestComputeRAGScore:
    def test_empty_context_returns_zero(self) -> None:
        assert _compute_rag_score([]) == 0.0

    def test_single_high_score_result(self) -> None:
        ctx = [{"score": 0.9}]
        score = _compute_rag_score(ctx)
        assert 0.5 < score <= 1.0

    def test_single_low_score_result(self) -> None:
        ctx = [{"score": 0.1}]
        score = _compute_rag_score(ctx)
        assert score < 0.3

    def test_multiple_high_scores_get_bonus(self) -> None:
        ctx_many = [{"score": 0.8}, {"score": 0.8}, {"score": 0.8}]
        ctx_one = [{"score": 0.8}]
        assert _compute_rag_score(ctx_many) > _compute_rag_score(ctx_one)

    def test_score_capped_at_one(self) -> None:
        ctx = [{"score": 1.0}] * 10
        assert _compute_rag_score(ctx) <= 1.0


# ---------------------------------------------------------------------------
# _generate_search_queries tests
# ---------------------------------------------------------------------------


class TestGenerateSearchQueries:
    def test_returns_original_query(self) -> None:
        queries = _generate_search_queries("G4Box geometry")
        assert "G4Box geometry" in queries

    def test_strips_fillers(self) -> None:
        queries = _generate_search_queries("How to create a cylinder detector")
        assert len(queries) >= 1
        # Should have a simplified version
        simplified = queries[-1].lower()
        assert "how to" not in simplified

    def test_max_three_queries(self) -> None:
        queries = _generate_search_queries("test query")
        assert len(queries) <= 3


# ---------------------------------------------------------------------------
# retrieve_rag_context integration test (with mocked Ollama)
# ---------------------------------------------------------------------------


class TestRetrieveRAGContext:
    async def test_graceful_fallback_when_ollama_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When Ollama is unreachable, must return score 0.0 and needs_web=True."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        reset_rag_client()

        # Mock OllamaEmbedder to report unavailable
        with patch("agent_core.context.nodes.OllamaEmbedder") as mock_cls:
            mock_embedder = AsyncMock(spec=OllamaEmbedder)
            mock_embedder.is_available = AsyncMock(return_value=False)
            mock_cls.return_value = mock_embedder

            state: dict[str, Any] = {
                "user_query": "G4Box detector geometry",
                "job_id": "test_rag_fallback",
            }
            result = await retrieve_rag_context(state)

            assert result["rag_score"] == 0.0
            assert result["needs_web_supplement"] is True
            assert result["rag_report"]["ollama_available"] is False
            assert len(result["rag_context"]) == 0

    async def test_returns_results_when_ollama_available(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When Ollama is available and indexed, must return real results."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        reset_rag_client()

        # Build a real index with known docs
        idx = DocumentIndex()
        docs = [
            _make_doc("g4_box", "G4Box", "G4Box box solid geometry detector"),
            _make_doc("g4_mat", "Material", "G4NistManager material database"),
        ]
        # Box doc aligned with [1,0], Material aligned with [0,1]
        doc_embs = [
            np.array([1.0, 0.0, 0.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0, 0.0, 0.0]),
        ]
        idx.add_documents(docs, doc_embs)

        # Mock embedder: query "box" maps to same direction as box doc
        mock_embedder = AsyncMock(spec=OllamaEmbedder)
        mock_embedder.is_available = AsyncMock(return_value=True)
        mock_embedder.embed = AsyncMock(return_value=np.array([0.95, 0.05, 0.0, 0.0, 0.0]))
        mock_embedder.embed_batch = AsyncMock(return_value=[
            np.array([1.0, 0.0, 0.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0, 0.0, 0.0]),
        ])

        client = RAGClient(embedder=mock_embedder, index=idx)

        with patch("agent_core.context.nodes._get_rag_client", return_value=client):
            state: dict[str, Any] = {
                "user_query": "box geometry detector",
                "job_id": "test_rag_real",
            }
            result = await retrieve_rag_context(state)

            assert result["rag_score"] > 0.0, "Score must be > 0 with matching results"
            assert len(result["rag_context"]) >= 1
            assert result["rag_report"]["ollama_available"] is True
            assert result["rag_report"]["engine"] == "ollama_bge_m3"

            # Top result should be box doc
            top = result["rag_context"][0]
            assert top["doc_id"] == "g4_box"
            assert top["score"] > 0.5

    async def test_saves_rag_files_to_disk(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """RAG context and report must be persisted to disk."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        reset_rag_client()

        with patch("agent_core.context.nodes.OllamaEmbedder") as mock_cls:
            mock_embedder = AsyncMock(spec=OllamaEmbedder)
            mock_embedder.is_available = AsyncMock(return_value=False)
            mock_cls.return_value = mock_embedder

            state: dict[str, Any] = {
                "user_query": "test",
                "job_id": "test_files",
            }
            await retrieve_rag_context(state)

            context_dir = tmp_path / "jobs" / "test_files" / "01_context"
            assert (context_dir / "rag_context.json").exists()
            assert (context_dir / "rag_sufficiency.json").exists()

            report = json.loads((context_dir / "rag_sufficiency.json").read_text())
            assert "ollama_available" in report
            assert "engine" in report


# ---------------------------------------------------------------------------
# Live Ollama test (marked integration — only runs if Ollama is up)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestLiveOllamaRAG:
    async def test_live_embed_and_search(self) -> None:
        """Live test: embed query via Ollama, search Geant4 doc store."""
        embedder = OllamaEmbedder()
        if not await embedder.is_available():
            pytest.skip("Ollama not available at localhost:11434")

        store = Geant4DocStore()
        docs = store.get_documents()
        assert len(docs) > 0

        client = RAGClient(embedder=embedder)
        count = await client.index_documents(docs)
        assert count > 0, "Should index at least some documents"

        results = await client.search("G4Box box solid geometry", top_k=3)
        assert len(results) > 0, "Should find at least one result for G4Box query"
        assert results[0].score > 0.3, f"Top result score too low: {results[0].score}"

        # Box doc should rank high
        top_ids = [r.doc_id for r in results[:3]]
        assert any("box" in tid for tid in top_ids), f"Expected box in top results: {top_ids}"
