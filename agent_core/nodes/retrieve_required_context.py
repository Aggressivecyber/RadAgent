"""Retrieve context for all required RAG sources in a single node.

Replaces the old fan-out (retrieve_g4/tcad/spice_context) with a unified
node that dynamically retrieves only from required_sources.

MVP-1 scope: Geant4 only. TCAD/SPICE are stubs that return empty context.
"""

from __future__ import annotations

import json
import logging

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState
from agent_core.tools.geant4_rag_tool import Geant4RAGTool
from agent_core.tools.spice_rag_tool import SpiceTool
from agent_core.tools.tcad_rag_tool import TcadTool

logger = logging.getLogger(__name__)

_TOOL_MAP: dict[str, type] = {
    "geant4": Geant4RAGTool,
    "tcad": TcadTool,
    "spice": SpiceTool,
}


async def _retrieve_source(
    source: str,
    user_query: str,
    task_spec: dict,
    rag_registry: dict,
    job_id: str,
) -> list[dict]:
    """Retrieve context from a single RAG source. Returns empty if not needed."""
    tool_cls = _TOOL_MAP.get(source)
    if tool_cls is None:
        logger.warning("Unknown RAG source: %s", source)
        return []

    # Check registry availability
    sources = rag_registry.get("sources", {})
    source_info = sources.get(source, {})
    if not source_info.get("available", False) and source != "geant4":
        # TCAD/SPICE stubs always have available=False, that's fine
        pass

    tool = tool_cls()
    if not tool.available and source != "geant4":
        # Stub tools have available=False; skip
        return []

    context_pack = await tool.build_context_pack(user_query, task_spec)

    # Save per-source context
    job_dir = get_job_dir(job_id)
    ctx_file = job_dir / "01_context" / f"{source}_context.json"
    ctx_file.write_text(
        json.dumps(context_pack, indent=2, ensure_ascii=False, default=str)
    )

    # Flatten into context list
    retrieved = context_pack.get("retrieved_context", {})
    context: list[dict] = []
    context.extend(retrieved.get("manual_snippets", []))
    context.extend(retrieved.get("example_code", []))
    context.extend(retrieved.get("data_contracts", []))
    return context


async def retrieve_required_context(state: RadiationAgentState) -> dict:
    """Retrieve context for all required and optional RAG sources.

    Only retrieves from sources listed in rag_required_sources /
    rag_optional_sources.  Non-required sources return empty context
    and do not affect the sufficiency score.
    """
    rag_required = state.get("rag_required_sources", [])
    rag_optional = state.get("rag_optional_sources", [])
    all_sources = list(dict.fromkeys(rag_required + rag_optional))

    user_query = state.get("user_query", "")
    task_spec = state.get("task_spec", {})
    job_id = state.get("job_id", "unknown")
    rag_registry = state.get("rag_registry", {})

    results: dict[str, list[dict]] = {
        "g4_context": [],
        "tcad_context": [],
        "spice_context": [],
    }

    for source in all_sources:
        context = await _retrieve_source(
            source, user_query, task_spec, rag_registry, job_id,
        )
        state_key = f"{source}_context"
        # Map logical names to state keys
        key_map = {"geant4": "g4_context", "tcad": "tcad_context", "spice": "spice_context"}
        state_key = key_map.get(source, state_key)
        results[state_key] = context

    return {
        **results,
        "current_node": "retrieve_required_context",
    }
