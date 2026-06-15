"""Retired native Geant4 visual review gate.

The browser 3D model view replaced the native Geant4 workbench approval flow.
This module remains as a compatibility shim for older imports and tests.
"""

from __future__ import annotations

from typing import Any

from .schemas import GateSubgraphState

GATE_ID = 21


async def run_visual_review_gate(state: GateSubgraphState) -> dict[str, Any]:
    """Return existing gate state without adding the retired visual gate."""
    gate_results: list[dict[str, Any]] = list(state.get("gate_results", []))
    failed: list[Any] = list(state.get("failed_gates", []))
    return {"gate_results": gate_results, "failed_gates": failed}
