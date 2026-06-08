"""RAG endpoint registry with auto-discovery."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RAGSourceStatus:
    name: str
    endpoint: str
    available: bool = False
    last_checked: float = 0.0
    error: str = ""


class RAGRegistry:
    """Auto-discover and track RAG endpoint availability."""

    # Logical source names to env var mapping
    _SOURCE_ENV: dict[str, str] = {
        "geant4": "GEANT4_RAG_ENDPOINT",
        "tcad": "TCAD_RAG_ENDPOINT",
        "spice": "SPICE_RAG_ENDPOINT",
    }

    def __init__(self) -> None:
        self.sources: dict[str, RAGSourceStatus] = {}
        self._load_from_env()

    def _load_from_env(self) -> None:
        """Load endpoints from environment variables."""
        for name, env_var in self._SOURCE_ENV.items():
            endpoint = os.environ.get(env_var, "")
            self.sources[name] = RAGSourceStatus(
                name=name,
                endpoint=endpoint,
                available=False,  # Not checked yet
            )

    async def discover_all(self) -> dict[str, dict]:
        """Probe all endpoints for availability. Returns serializable dict."""
        import httpx

        for name, status in self.sources.items():
            if not status.endpoint:
                status.available = False
                status.error = "No endpoint configured"
                continue
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{status.endpoint}/health")
                    status.available = resp.status_code == 200
                    status.error = "" if status.available else f"HTTP {resp.status_code}"
            except Exception as exc:
                status.available = False
                status.error = str(exc)[:100]
            status.last_checked = time.time()

        return self.to_dict()

    def is_available(self, source_name: str) -> bool:
        return self.sources.get(source_name, RAGSourceStatus("", "")).available

    def get_endpoint(self, source_name: str) -> str | None:
        status = self.sources.get(source_name)
        return status.endpoint if status else None

    def to_dict(self) -> dict[str, dict]:
        return {
            name: {
                "endpoint": s.endpoint,
                "available": s.available,
                "last_checked": s.last_checked,
                "error": s.error,
            }
            for name, s in self.sources.items()
        }
