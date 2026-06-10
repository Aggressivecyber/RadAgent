"""Workflow-aware RadAgent copilot with RAG, web search, and job history.

Each turn:
  1. Injects workflow context when available
  2. Searches Geant4 RAG for relevant context
  3. Optionally searches the web
  4. Gathers recent job summaries
  5. Builds an enriched system prompt with all context
  6. Calls the LLM with full conversation history
  7. Returns the response and updates history
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from agent_core.chat.prompts import CHAT_SYSTEM_PROMPT
from agent_core.workspace.paths import STAGE_INPUT, STAGE_REPORT

logger = logging.getLogger(__name__)

# Max conversation turns to keep in context window
_MAX_HISTORY_TURNS = 20


class ChatAgent:
    """Stateful workflow copilot with read-only context tools.

    Lifecycle:
      - Created once per REPL session
      - Maintains conversation history across turns
      - Resets when a new job starts (``reset()``)
    """

    def __init__(self) -> None:
        self.history: list[dict[str, str]] = []
        self._rag: Any = None  # RAGClient | None
        self._rag_initialized = False
        self._web: Any = None  # WebSearchTool | None
        self._doc_store_loaded = False

    # ── Public API ──────────────────────────────────────────────────

    async def chat(
        self,
        user_message: str,
        *,
        workflow_context: dict[str, Any] | None = None,
    ) -> str:
        """Process a user message and return a workflow-aware response string.

        Searches RAG + web for context, gathers job history,
        then calls the LLM with full conversation history.
        """
        from agent_core.models.client import call_multi_turn_chat
        from agent_core.models.config import load_model_profiles
        from agent_core.models.schemas import ModelTier

        profiles = load_model_profiles()
        profile = profiles[ModelTier.LITE]

        # Gather context (RAG + web + jobs) in parallel
        rag_results, web_results, jobs = await asyncio.gather(
            self._search_rag(user_message),
            self._search_web(user_message),
            self._get_recent_jobs_async(),
        )

        # Build messages array
        system_prompt = self._build_system_prompt(
            rag_results,
            web_results,
            jobs,
            workflow_context=workflow_context,
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

        # Add conversation history (trim to avoid context overflow)
        trimmed = self.history[-_MAX_HISTORY_TURNS * 2 :]
        messages.extend(trimmed)
        messages.append({"role": "user", "content": user_message})

        # Call LLM
        try:
            response = await call_multi_turn_chat(profile, messages)
        except Exception as exc:
            logger.exception("Chat agent LLM call failed")
            return f"[对话服务暂时不可用: {exc}]"

        # Update history
        self.history.append({"role": "user", "content": user_message})
        self.history.append({"role": "assistant", "content": response})

        return response

    def reset(self) -> None:
        """Clear conversation history (called when a new job starts)."""
        self.history.clear()

    # ── RAG search ──────────────────────────────────────────────────

    _CACHE_DIR = "simulation_workspace/.cache"

    async def _ensure_rag(self) -> Any:
        """Lazily initialize the RAG client with Geant4 documents.

        Embeddings are cached to disk so subsequent startups are instant.
        """
        if self._rag_initialized:
            return self._rag
        self._rag_initialized = True

        try:
            from agent_core.context.doc_store import Geant4DocStore
            from agent_core.context.rag_client import RAGClient

            rag = RAGClient()
            if not await rag.backend_available():
                logger.info("Ollama not available, RAG disabled for chat")
                return None

            if not self._doc_store_loaded:
                store = Geant4DocStore()
                docs = store.get_documents()

                # Try loading cached embeddings
                loaded = self._load_cached_embeddings(rag, docs)
                if loaded:
                    logger.info("Chat RAG: loaded %d cached embeddings", rag.index.size)
                else:
                    # Slow path: embed via Ollama
                    count = await rag.index_documents(docs)
                    logger.info("Chat RAG: indexed %d Geant4 documents", count)
                    self._save_embeddings_cache(rag, docs)

                self._doc_store_loaded = True

            self._rag = rag
            return rag
        except Exception as exc:
            logger.warning("Chat RAG init failed: %s", exc)
            return None

    def _load_cached_embeddings(self, rag: Any, docs: list) -> bool:
        """Load embeddings from cache. Returns True on success."""
        import hashlib
        from pathlib import Path

        import numpy as np

        from agent_core.context.rag_client import RAGDocument

        cache_dir = Path(self._CACHE_DIR)
        cache_file = cache_dir / "g4_doc_embeddings.npz"
        hash_file = cache_dir / "g4_doc_hash.txt"

        if not cache_file.exists() or not hash_file.exists():
            return False

        # Check if documents changed (hash of doc_ids + content)
        doc_hash = hashlib.sha256(
            "|".join(d.doc_id + d.content for d in docs).encode()
        ).hexdigest()[:16]

        saved_hash = hash_file.read_text().strip()
        if doc_hash != saved_hash:
            return False

        try:
            data = np.load(cache_file)
            embeddings = data["embeddings"]
            if embeddings.shape[0] != len(docs):
                return False

            from agent_core.context.rag_client import RAGDocument

            rag_docs = [
                RAGDocument(
                    doc_id=d.doc_id,
                    title=d.title,
                    content=d.content,
                    source=d.source,
                    metadata=d.metadata,
                )
                for d in docs
            ]
            rag.index.add_documents(rag_docs, list(embeddings))
            return True
        except Exception as exc:
            logger.warning("Cache load failed: %s", exc)
            return False

    def _save_embeddings_cache(self, rag: Any, docs: list) -> None:
        """Save computed embeddings to disk cache."""
        import hashlib
        from pathlib import Path

        import numpy as np

        if rag.index.size == 0:
            return

        cache_dir = Path(self._CACHE_DIR)
        cache_dir.mkdir(parents=True, exist_ok=True)

        cache_file = cache_dir / "g4_doc_embeddings.npz"
        hash_file = cache_dir / "g4_doc_hash.txt"

        try:
            # Save embeddings
            np.savez(cache_file, embeddings=rag.index._embeddings)

            # Save hash
            doc_hash = hashlib.sha256(
                "|".join(d.doc_id + d.content for d in docs).encode()
            ).hexdigest()[:16]
            hash_file.write_text(doc_hash)
            logger.info("Chat RAG: embeddings cached to %s", cache_file)
        except Exception as exc:
            logger.warning("Cache save failed: %s", exc)

    async def _search_rag(self, query: str) -> list[dict[str, Any]]:
        """Search Geant4 knowledge base for relevant context."""
        rag = await self._ensure_rag()
        if not rag:
            return []
        try:
            results = await rag.search(query, top_k=3, min_score=0.25)
            return [
                {
                    "title": r.title,
                    "content": r.content[:300],
                    "score": round(r.score, 3),
                }
                for r in results
            ]
        except Exception as exc:
            logger.warning("Chat RAG search failed: %s", exc)
            return []

    # ── Web search ──────────────────────────────────────────────────

    async def _search_web(self, query: str) -> list[dict[str, Any]]:
        """Search the web for supplementary information."""
        try:
            from agent_core.tools.web_search_tool import WebSearchTool

            if not self._web:
                self._web = WebSearchTool()
            if not self._web.search_available:
                return []
            results = await self._web.search(query, max_results=3)
            return [{"title": r.title, "snippet": r.snippet[:200], "url": r.url} for r in results]
        except Exception as exc:
            logger.warning("Chat web search failed: %s", exc)
            return []

    # ── Job history ─────────────────────────────────────────────────

    async def _get_recent_jobs_async(self) -> list[dict[str, Any]]:
        """Get summaries of recent jobs (runs in executor to avoid blocking)."""
        return await asyncio.to_thread(self._get_recent_jobs)

    def _get_recent_jobs(self) -> list[dict[str, Any]]:
        """Synchronous job listing."""
        try:
            from agent_core.storage import RadAgentStore

            store = RadAgentStore()
            store.import_existing_jobs()
            return [
                {
                    "id": job["job_id"],
                    "query": str(job["user_query"])[:100],
                    "done": job["status"] == "completed",
                }
                for job in store.list_jobs(limit=5)
            ]
        except Exception as exc:
            logger.warning("Database job listing failed: %s", exc)

        try:
            from agent_core.workspace.manager import WorkspaceManager

            ws = WorkspaceManager()
            jobs_dir = ws.root / "jobs"
            if not jobs_dir.exists():
                return []

            jobs: list[dict[str, Any]] = []
            for job_dir in sorted(jobs_dir.iterdir(), reverse=True):
                if not job_dir.is_dir() or len(jobs) >= 5:
                    continue
                query_file = job_dir / STAGE_INPUT / "user_query.md"
                query = ""
                if query_file.exists():
                    raw = query_file.read_text(encoding="utf-8").strip()
                    lines = raw.split("\n")
                    query = lines[-1].strip() if lines else raw[:80]
                jobs.append(
                    {
                        "id": job_dir.name,
                        "query": query[:100],
                        "done": (job_dir / STAGE_REPORT / "final_report.md").exists(),
                    }
                )
            return jobs
        except Exception as exc:
            logger.warning("Job listing failed: %s", exc)
            return []

    # ── Prompt assembly ─────────────────────────────────────────────

    def _build_system_prompt(
        self,
        rag_results: list[dict[str, Any]],
        web_results: list[dict[str, Any]],
        jobs: list[dict[str, Any]],
        *,
        workflow_context: dict[str, Any] | None = None,
    ) -> str:
        """Assemble system prompt with retrieved context."""
        parts = [CHAT_SYSTEM_PROMPT]

        if workflow_context:
            parts.append("### 当前工作流状态\n" + _format_workflow_context(workflow_context))

        if rag_results:
            lines = []
            for r in rag_results:
                lines.append(f"- **{r['title']}** (score: {r['score']}): {r['content']}")
            parts.append("### 知识库检索结果\n" + "\n".join(lines))

        if web_results:
            lines = []
            for r in web_results:
                lines.append(f"- **{r['title']}**: {r['snippet']} ({r['url']})")
            parts.append("### 网络搜索结果\n" + "\n".join(lines))

        if jobs:
            lines = []
            for j in jobs:
                status = "✓ 已完成" if j["done"] else "⏳ 进行中"
                lines.append(f"- `{j['id']}` — {status} — {j['query']}")
            parts.append("### 历史项目\n" + "\n".join(lines))
        else:
            parts.append("### 历史项目\n（暂无历史项目）")

        return "\n\n".join(parts)


def _format_workflow_context(context: dict[str, Any]) -> str:
    """Format workflow context compactly for model prompts."""
    lines = [
        f"job_id: {context.get('job_id', '')}",
        f"status: {context.get('status', '')}",
        f"current_phase: {context.get('current_phase', '')}",
        f"current_phase_idx: {context.get('current_phase_idx', '')}",
        f"needs_confirmation: {context.get('needs_confirmation', False)}",
    ]
    user_query = context.get("user_query")
    if user_query:
        lines.append(f"user_query: {user_query}")
    key_statuses = context.get("key_statuses")
    if key_statuses:
        lines.append("key_statuses: " + json.dumps(key_statuses, ensure_ascii=False))
    state = context.get("state")
    if isinstance(state, dict):
        if "unconfirmed_assumptions_count" in state:
            lines.append(
                "unconfirmed_assumptions_count: "
                f"{state.get('unconfirmed_assumptions_count')}"
            )
        if state.get("human_confirmation_required") is not None:
            lines.append(
                "human_confirmation_required: "
                f"{state.get('human_confirmation_required')}"
            )
    gate_results = context.get("gate_results")
    if gate_results:
        lines.append("gate_results: " + json.dumps(gate_results[:8], ensure_ascii=False))
    evidence = context.get("evidence")
    if evidence:
        lines.append("evidence: " + json.dumps(evidence, ensure_ascii=False))
    return "\n".join(lines)
