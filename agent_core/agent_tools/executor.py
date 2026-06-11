"""Direct executor for registered agent tools."""

from __future__ import annotations

import time
from typing import Any

from agent_core.agent_tools.registry import get_agent_tool_registry
from agent_core.agent_tools.selection import select_agent_tool_calls


def execute_selected_agent_tools(user_message: str) -> list[dict[str, Any]]:
    """Execute selected tools directly from the registry.

    This uses the same registry and selection contract as the LangGraph tool
    subgraph, but avoids running LangGraph's ToolNode inside worker threads.
    """
    registry = get_agent_tool_registry()
    results: list[dict[str, Any]] = []
    for call in select_agent_tool_calls(user_message):
        tool_name = str(call.get("name") or "")
        tool_call_id = str(call.get("id") or "")
        args = call.get("args") if isinstance(call.get("args"), dict) else {}
        start = time.time()
        try:
            payload = registry.get(tool_name).invoke(args)
            success = not (isinstance(payload, dict) and payload.get("error"))
            results.append(
                {
                    "tool": tool_name,
                    "success": success,
                    "payload": payload,
                    "tool_call_id": tool_call_id,
                    "latency_ms": round((time.time() - start) * 1000, 1),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "tool": tool_name,
                    "success": False,
                    "payload": {"error": str(exc)},
                    "tool_call_id": tool_call_id,
                    "latency_ms": round((time.time() - start) * 1000, 1),
                }
            )
    return results
