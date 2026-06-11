"""Tool-call selection for Copilot until model-native tool calls are enabled."""

from __future__ import annotations

from typing import Any

from agent_core.space_radiation.ap8ae8_provider import is_orbit_radiation_request


def select_agent_tool_calls(user_message: str) -> list[dict[str, Any]]:
    """Select deterministic agent tool calls for a user turn.

    This sits in front of the model-native tool-calling path. It keeps the
    registry/tool execution architecture in place while the current model client
    still exposes only plain chat completions.
    """
    if is_orbit_radiation_request(user_message):
        tool_name = "orbit_radiation_ap8ae8_query"
        return [
            {
                "name": tool_name,
                "args": {"message": user_message},
                "id": f"{tool_name}:0",
            }
        ]
    return []
