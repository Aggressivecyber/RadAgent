"""RAG source auto-discovery tool."""
from __future__ import annotations

import logging

from agent_core.config.rag_registry import RAGRegistry

logger = logging.getLogger(__name__)


async def discover_rag_sources() -> dict[str, dict]:
    """Discover available RAG sources and return status dict."""
    registry = RAGRegistry()
    result = await registry.discover_all()
    for name, status in result.items():
        state = "available" if status["available"] else f"unavailable ({status['error']})"
        logger.info("RAG source %s: %s", name, state)
    return result
