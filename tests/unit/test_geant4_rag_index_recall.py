from __future__ import annotations

import pickle
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock

import numpy as np
from agent_core.context.rag_client import DocumentIndex, OllamaEmbedder, RAGClient, _query_terms


def test_document_index_loads_prebuilt_sqlite(tmp_path: Path) -> None:
    db_path = tmp_path / "geant4_index.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE documents ("
        "id INTEGER PRIMARY KEY, source TEXT, title TEXT, content TEXT, "
        "embedding BLOB, metadata TEXT)"
    )
    conn.execute(
        "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)",
        (
            1,
            "appdev",
            "Geant4 Run Macros",
            "/run/initialize must appear before /run/beamOn.",
            pickle.dumps(np.array([1.0, 0.0], dtype=np.float32)),
            '{"path": "run.html"}',
        ),
    )
    conn.commit()
    conn.close()

    index = DocumentIndex()
    assert index.load_sqlite(db_path)
    assert index.size == 1
    assert index.embedding_dim == 2


async def test_hybrid_search_promotes_exact_geant4_api_terms() -> None:
    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed = AsyncMock(return_value=np.array([0.0, 1.0]))

    index = DocumentIndex()
    index.add_documents(
        documents=[
            _doc("semantic", "Generic geometry", "G4Box geometry placement"),
            _doc(
                "lexical",
                "G4Allocator hit allocation",
                "Use G4Allocator<Hit>::MallocSingle and FreeSingle for hit objects.",
            ),
        ],
        embeddings=[
            np.array([0.0, 1.0]),
            np.array([0.2, 0.8]),
        ],
    )
    client = RAGClient(embedder=embedder, index=index)

    results = await client.search("Geant4 G4Allocator MallocSingle FreeSingle", top_k=2)

    assert results[0].doc_id == "lexical"
    assert results[0].metadata["lexical_score"] > 0


async def test_lexical_supplemental_docs_can_beat_semantic_only_docs() -> None:
    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed = AsyncMock(return_value=np.array([1.0, 0.0]))

    index = DocumentIndex()
    index.add_documents(
        documents=[
            _doc("semantic", "Container guide", "Generic output files in a directory"),
        ],
        embeddings=[np.array([1.0, 0.0])],
    )
    added = index.add_lexical_documents(
        [
            _doc(
                "radagent_contract",
                "RadAgent G4_OUTPUT_DIR output contract",
                "G4_OUTPUT_DIR output.csv run_summary.json metadata.json",
            )
        ]
    )
    client = RAGClient(embedder=embedder, index=index)

    results = await client.search("G4_OUTPUT_DIR output.csv run_summary.json metadata.json")

    assert added == 1
    assert results[0].doc_id == "radagent_contract"
    assert results[0].metadata["lexical_score"] == 1.0


async def test_output_manager_repair_query_promotes_runtime_contract_docs() -> None:
    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed = AsyncMock(return_value=np.array([1.0, 0.0]))

    index = DocumentIndex()
    index.add_documents(
        documents=[
            _doc(
                "sqlite:geometry",
                "Geometry",
                "Geometry source physics volume navigation scoring output pattern.",
            ),
        ],
        embeddings=[np.array([1.0, 0.0])],
    )
    index.add_lexical_documents(
        [
            _doc(
                "g4_output_contract",
                "RadAgent Geant4 Output Contract",
                "G4_OUTPUT_DIR output.csv run_summary.json metadata.json "
                "EventID,edep_MeV,dose_Gy OutputManager",
            )
        ]
    )
    client = RAGClient(embedder=embedder, index=index)

    results = await client.search(
        "Geant4 output_manager repair ScoringManager G4_OUTPUT_DIR "
        "output.csv run_summary.json metadata.json EventID edep_MeV dose_Gy",
        top_k=2,
    )

    assert results[0].doc_id == "g4_output_contract"


def test_query_terms_keep_geant4_api_filenames_and_runtime_artifacts() -> None:
    terms = _query_terms(
        "SensitiveDetector.cc must include G4THitsCollection.hh and "
        "G4Allocator<Hit>; write output.csv run_summary.json metadata.json "
        "under G4_OUTPUT_DIR after /run/initialize."
    )

    assert "sensitivedetector.cc" in terms.exact
    assert "g4thitscollection.hh" in terms.exact
    assert "g4allocator<hit>" in terms.exact
    assert "output.csv" in terms.exact
    assert "run_summary.json" in terms.exact
    assert "metadata.json" in terms.exact
    assert "g4_output_dir" in terms.exact
    assert "/run/initialize" in terms.exact


async def test_search_falls_back_to_lexical_when_embedding_fails() -> None:
    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed = AsyncMock(return_value=None)

    index = DocumentIndex()
    index.add_documents(
        documents=[
            _doc("generic", "Generic", "Generic detector material information."),
            _doc(
                "hits",
                "G4THitsCollection hit collections",
                "SensitiveDetector.cc must include G4THitsCollection.hh.",
            ),
        ],
        embeddings=[
            np.array([1.0, 0.0]),
            np.array([0.0, 1.0]),
        ],
    )
    client = RAGClient(embedder=embedder, index=index)

    results = await client.search(
        "Geant4 repair SensitiveDetector.cc G4THitsCollection.hh",
        top_k=2,
    )

    assert results
    assert results[0].doc_id == "hits"
    assert results[0].metadata["semantic_score"] == 0.0
    assert results[0].metadata["lexical_score"] > 0.0


async def test_strong_manual_hit_expands_adjacent_chunks() -> None:
    embedder = AsyncMock(spec=OllamaEmbedder)
    embedder.embed = AsyncMock(return_value=np.array([0.0, 1.0]))

    index = DocumentIndex()
    docs = [
        _doc(
            "sqlite:10",
            "Hits",
            "Previous chunk explains allocator ownership and collection lifecycle.",
            metadata={"path": "Detector/hits.html"},
        ),
        _doc(
            "sqlite:11",
            "Hits",
            "G4THitsCollection.hh and G4Allocator<Hit> are used for hits.",
            metadata={"path": "Detector/hits.html"},
        ),
        _doc(
            "sqlite:12",
            "Hits",
            "Next chunk shows MallocSingle and FreeSingle operators.",
            metadata={"path": "Detector/hits.html"},
        ),
    ]
    index.add_documents(
        documents=docs,
        embeddings=[
            np.array([0.0, 1.0]),
            np.array([0.0, 1.0]),
            np.array([0.0, 1.0]),
        ],
    )
    client = RAGClient(embedder=embedder, index=index)

    results = await client.search(
        "Geant4 G4THitsCollection.hh G4Allocator<Hit> MallocSingle FreeSingle",
        top_k=1,
    )

    assert results[0].doc_id == "sqlite:11"
    assert "Previous chunk explains allocator ownership" in results[0].content
    assert "Next chunk shows MallocSingle" in results[0].content
    assert results[0].metadata["expanded_doc_ids"] == [
        "sqlite:10",
        "sqlite:11",
        "sqlite:12",
    ]


def _doc(
    doc_id: str,
    title: str,
    content: str,
    metadata: dict | None = None,
):
    from agent_core.context.rag_client import RAGDocument

    return RAGDocument(
        doc_id=doc_id,
        title=title,
        content=content,
        source="test",
        metadata=metadata or {},
    )
