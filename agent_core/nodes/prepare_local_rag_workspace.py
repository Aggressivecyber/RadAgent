"""Prepare local RAG workspace — check and load knowledge_base directories.

Runs as the first node in the LangGraph pipeline.
Checks that knowledge_base/{geant4,tcad,spice}/ exist and loads rag_registry.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent_core.graph.state import RadiationAgentState

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_KB_DIR = _PROJECT_ROOT / "knowledge_base"
_REGISTRY_PATH = _PROJECT_ROOT / "agent_core" / "config" / "rag_registry.json"

_REQUIRED_DIRS: dict[str, str] = {
    "geant4": "Geant4",
    "tcad": "TCAD",
    "spice": "SPICE",
}


async def prepare_local_rag_workspace(state: RadiationAgentState) -> dict:
    """Check local knowledge_base and load rag_registry into state."""
    registry: dict[str, Any] = {}

    # Load rag_registry.json if it exists
    if _REGISTRY_PATH.is_file():
        try:
            registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load rag_registry.json: %s", exc)

    sources = registry.get("sources", {})

    # Verify each source directory actually exists on disk
    validation_errors: list[str] = []
    for name, info in sources.items():
        kb_path = _PROJECT_ROOT / info.get("path", f"knowledge_base/{name}")
        if not kb_path.is_dir():
            info["available"] = False
            validation_errors.append(
                f"RAG source '{name}': directory {kb_path} does not exist"
            )
        else:
            # Check at least 1 non-cache file exists
            has_content = any(
                p.is_file()
                for p in kb_path.rglob("*")
                if "__pycache__" not in str(p) and ".ruff_cache" not in str(p)
            )
            if not has_content:
                info["available"] = False
                validation_errors.append(
                    f"RAG source '{name}': directory exists but contains no files"
                )
            else:
                info["available"] = True

    # Determine execution mode based on Geant4 availability
    g4_available = sources.get("geant4", {}).get("available", False)
    execution_mode = "mvp1_acceptance" if g4_available else "dev_no_geant4_env"

    log_msg = (
        f"RAG workspace ready: {sum(1 for s in sources.values() if s.get('available'))} sources, "
        f"mode={execution_mode}"
    )
    logger.info(log_msg)

    return {
        "rag_registry": registry,
        "execution_mode": execution_mode,
        "errors": validation_errors,
        "current_node": "prepare_local_rag_workspace",
    }
