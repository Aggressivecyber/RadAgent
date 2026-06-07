"""Chat agent — conversational AI with RAG, web search, and job history.

Provides a stateful chat experience for the REPL's smalltalk/unknown intents.
Each turn:
  1. Searches Geant4 RAG for relevant context
  2. Optionally searches the web
  3. Gathers recent job summaries
  4. Builds an enriched system prompt with all context
  5. Calls the LLM with full conversation history
  6. Returns the response and updates history
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_core.chat.prompts import CHAT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# Max conversation turns to keep in context window
_MAX_HISTORY_TURNS = 20


class ChatAgent:
    """Stateful conversational agent with tool access.

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

    async def chat(self, user_message: str) -> str:
        """Process a user message and return a response string.

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
        system_prompt = self._build_system_prompt(rag_results, web_results, jobs)
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

    async def _ensure_rag(self) -> Any:
        """Lazily initialize the RAG client with Geant4 documents."""
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
                count = await rag.index_documents(docs)
                logger.info("Chat RAG: indexed %d Geant4 documents", count)
                self._doc_store_loaded = True

            self._rag = rag
            return rag
        except Exception as exc:
            logger.warning("Chat RAG init failed: %s", exc)
            return None

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
            return [
                {"title": r.title, "snippet": r.snippet[:200], "url": r.url}
                for r in results
            ]
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
            from agent_core.workspace.manager import WorkspaceManager

            ws = WorkspaceManager()
            jobs_dir = ws.root / "jobs"
            if not jobs_dir.exists():
                return []

            jobs: list[dict[str, Any]] = []
            for job_dir in sorted(jobs_dir.iterdir(), reverse=True):
                if not job_dir.is_dir():
                    continue
                if len(jobs) >= 5:
                    break

                query_file = job_dir / "00_input" / "user_query.md"
                report_file = job_dir / "10_report" / "final_report.md"

                query = ""
                if query_file.exists():
                    raw = query_file.read_text(encoding="utf-8").strip()
                    # Strip markdown header if present
                    lines = raw.split("\n")
                    query = lines[-1].strip() if lines else raw[:80]

                done = report_file.exists()
                jobs.append({
                    "id": job_dir.name,
                    "query": query[:100],
                    "done": done,
                })
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
    ) -> str:
        """Assemble system prompt with retrieved context."""
        parts = [CHAT_SYSTEM_PROMPT]

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
