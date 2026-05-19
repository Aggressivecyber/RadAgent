"""Geant4 文档语义搜索 + 关键词搜索（从 geant4-rag MCP 提取）"""

import json
import pickle
import sqlite3
from pathlib import Path

import numpy as np

DB_PATH = Path(__file__).parent / "data" / "geant4_index.db"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"


def _get_embedding(text: str) -> list[float]:
    import urllib.request

    if len(text) > 8000:
        text = text[:8000]

    payload = json.dumps({"model": EMBED_MODEL, "input": text}).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        embeddings = result.get("embeddings", [[]])
        if embeddings and embeddings[0]:
            return embeddings[0]
        return result.get("embedding", embeddings[0] if embeddings else [])


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def search_geant4(query: str, top_k: int = 5) -> list[dict]:
    if not DB_PATH.exists():
        return []

    query_emb = np.array(_get_embedding(query), dtype=np.float32)

    conn = sqlite3.connect(str(DB_PATH))
    try:
        c = conn.cursor()
        c.execute("SELECT id, source, title, content, embedding, metadata FROM documents")
        rows = c.fetchall()

        results = []
        for row in rows:
            doc_id, source, title, content, emb_blob, metadata = row
            try:
                doc_emb = pickle.loads(emb_blob)
                score = _cosine_similarity(query_emb, doc_emb)
                results.append({
                    "doc_id": doc_id,
                    "source": source,
                    "title": title,
                    "content": content[:500] + "..." if len(content) > 500 else content,
                    "relevance_score": round(score, 4),
                })
            except Exception:
                continue

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:top_k]
    finally:
        conn.close()


def keyword_search_geant4(keyword: str, top_k: int = 10) -> list[dict]:
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(str(DB_PATH))
    try:
        c = conn.cursor()
        c.execute(
            "SELECT id, source, title, content FROM documents "
            "WHERE content LIKE ? OR title LIKE ? "
            "ORDER BY id LIMIT ?",
            (f"%{keyword}%", f"%{keyword}%", top_k),
        )
        rows = c.fetchall()

        return [
            {"doc_id": row[0], "source": row[1], "title": row[2], "content": row[3][:500]}
            for row in rows
        ]
    finally:
        conn.close()
