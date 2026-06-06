"""Geant4 RAG tool — interfaces with the g4rag MCP server with local fallback."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

import httpx

from agent_core.schemas.rag_context_pack import RetrievedContext, compute_sufficiency

logger = logging.getLogger(__name__)

_LOCAL_DIR = Path(__file__).resolve().parents[2] / "knowledge_base" / "geant4"
_TIMEOUT = 15.0


class G4RAGTool:
    """Async client for the Geant4 RAG MCP server with local file fallback."""

    def __init__(self, endpoint: str | None = None) -> None:
        self._endpoint = endpoint or os.environ.get("G4RAG_MCP_ENDPOINT")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient | None:
        if self._client is None and self._endpoint:
            self._client = httpx.AsyncClient(base_url=self._endpoint, timeout=_TIMEOUT)
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search g4rag knowledge base; falls back to local on error."""
        client = await self._get_client()
        if client:
            try:
                r = await client.post("/search", json={"query": query, "top_k": top_k})
                r.raise_for_status()
                return r.json().get("results", [])
            except Exception:
                logger.warning("MCP search failed, using local fallback", exc_info=True)
        return self._local_search(query, top_k)

    async def get_manual_snippets(self, topic: str) -> list[dict]:
        results = await self.search(f"manual {topic}", top_k=5)
        return [
            {
                "text": r.get("text", ""),
                "source": r.get("source", ""),
                "page": r.get("page"),
                "source_type": "manual",
                "doc_type": r.get("doc_type", "manual"),
            }
            for r in results if r.get("doc_type") in ("manual", "book", "local", None)
        ]

    async def get_example_code(self, task_description: str) -> list[dict]:
        results = await self.search(f"example code {task_description}", top_k=5)
        return [
            {
                "code": r.get("code", r.get("text", "")),
                "language": r.get("language", "cpp"),
                "source": r.get("source", ""),
                "description": r.get("description", ""),
                "source_type": "example_code",
                "doc_type": r.get("doc_type", "example_code"),
            }
            for r in results if r.get("doc_type") in ("example", "code", "local", None)
        ]

    async def get_data_contract_info(self) -> list[dict]:
        results = await self.search("Geant4 output data contract format", top_k=3)
        if results:
            return [
                {
                    "contract_name": "g4_output_v1",
                    "schema": r.get("text", ""),
                    "source": r.get("source", ""),
                    "source_type": "data_contract",
                    "doc_type": r.get("doc_type", "contract"),
                }
                for r in results
            ]
        return [
            {
                "contract_name": "g4_output_v1",
                "schema": "edep, dose, event_table files with unit metadata",
                "source": "builtin_default",
                "source_type": "data_contract",
                "doc_type": "contract",
            }
        ]

    async def build_context_pack(self, query: str, task_spec: dict[str, Any]) -> dict[str, Any]:
        """Build a complete RAG context pack for Geant4 code generation."""
        ctx = RetrievedContext(
            manual_snippets=await self.get_manual_snippets(query),
            example_code=await self.get_example_code(query),
            data_contracts=await self.get_data_contract_info(),
        )
        suff = compute_sufficiency(ctx)
        return {
            "job_id": task_spec.get("simulation_id", uuid.uuid4().hex[:12]),
            "target_module": "geant4",
            "retrieved_context": ctx.model_dump(),
            "sufficiency": suff.model_dump(),
            "query_used": query,
            "sources_queried": [self._endpoint or "local_fallback"],
        }

    def _local_search(self, query: str, top_k: int) -> list[dict]:
        """Fallback: keyword search over local knowledge_base/geant4/ files.

        Searches .md, .jsonl, and .py files for relevant content.
        """
        if not _LOCAL_DIR.is_dir():
            return []
        terms = query.lower().split()
        hits: list[dict] = []
        search_extensions = {".md", ".jsonl", ".py", ".txt"}

        for p in sorted(_LOCAL_DIR.rglob("*")):
            if p.suffix not in search_extensions:
                continue
            if "__pycache__" in str(p) or ".ruff_cache" in str(p):
                continue
            try:
                text = p.read_text(errors="ignore")
            except Exception:
                continue

            if p.suffix == ".jsonl":
                # Each line is a JSON doc — search line by line
                for line_no, line in enumerate(text.splitlines()):
                    line_lower = line.lower()
                    n = sum(1 for t in terms if t in line_lower)
                    if n:
                        hits.append({
                            "text": line[:2000],
                            "source": f"{p.relative_to(_LOCAL_DIR)}#L{line_no}",
                            "score": n / max(len(terms), 1),
                            "doc_type": "local",
                        })
            else:
                n = sum(1 for t in terms if t in text.lower())
                if n:
                    hits.append({
                        "text": text[:2000],
                        "source": str(p.relative_to(_LOCAL_DIR)),
                        "score": n / max(len(terms), 1),
                        "doc_type": "local",
                    })

        hits.sort(key=lambda r: r["score"], reverse=True)
        return hits[:top_k]
