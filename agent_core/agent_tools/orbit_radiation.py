"""Orbit-radiation tools exposed to Copliot."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool

from agent_core.chat.orbit_radiation_tool import query_orbit_radiation


@tool("orbit_radiation_ap8ae8_query")
def orbit_radiation_ap8ae8_query(message: str) -> dict[str, Any]:
    """Query local AP8/AE8 trapped proton/electron radiation context for a user question.

    Use this for orbit radiation, trapped belt, Van Allen belt, AP8, AE8, L-shell,
    B/B0, TLE, or space-radiation source questions. The tool is read-only and
    reports selected model, known parameters, missing fields, next questions,
    and AP8/AE8 limitations; it does not create simulation artifacts.
    """
    result = query_orbit_radiation(message)
    if result is None:
        return {
            "tool": "orbit_radiation_ap8ae8_query",
            "ready": False,
            "skipped": True,
            "missing_fields": [],
            "notes": ["The message does not look like an orbit radiation request."],
        }
    return result
