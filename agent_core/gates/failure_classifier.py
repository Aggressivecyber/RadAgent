"""Classify gate failures for retry routing.

Maps failed gate IDs to the subgraph that should handle the retry:
- Gate 0 → context_subgraph
- Gate 1 → task_planning_subgraph
- Gate 2 → g4_modeling_subgraph
- Gate 3-4 → patch_subgraph
- Gate 5-11 → g4_codegen_subgraph, except Gate 10 → patch_subgraph
- Gate 7-11 → g4_codegen_subgraph for runtime/code contract repair
- G4-A to G4-E (12-16) → g4_modeling_subgraph
- G4-F to G4-G (17-18) → g4_codegen_subgraph
- G4-H (19) → requirements_review
"""

from __future__ import annotations

import re
from typing import Any

from .base_gates import GATE_NAMES, gate_name

# Gate ID → target subgraph for retry
_GATE_RETRY_MAP: dict[int, str] = {
    0: "context_subgraph",
    1: "task_planning_subgraph",
    2: "g4_modeling_subgraph",
    3: "patch_subgraph",
    4: "patch_subgraph",
    5: "g4_codegen_subgraph",
    6: "g4_codegen_subgraph",
    7: "g4_codegen_subgraph",
    8: "g4_codegen_subgraph",
    9: "g4_codegen_subgraph",
    10: "patch_subgraph",
    11: "g4_codegen_subgraph",
    12: "g4_modeling_subgraph",
    13: "g4_modeling_subgraph",
    14: "g4_modeling_subgraph",
    15: "g4_modeling_subgraph",
    16: "g4_modeling_subgraph",
    17: "g4_codegen_subgraph",
    18: "g4_codegen_subgraph",
    19: "requirements_review",
}


def classify_failure(failed_gate_ids: list[int]) -> str:
    """Classify gate failures and return the primary retry target subgraph.

    Uses the highest-priority gate (lowest ID) to determine retry target.
    Priority: context > modeling > codegen > patch
    """
    if not failed_gate_ids:
        return "report_subgraph"

    # Sort by priority (lowest gate ID = highest priority)
    sorted_gates = sorted(failed_gate_ids)

    primary_gate = sorted_gates[0]
    return _GATE_RETRY_MAP.get(primary_gate, "report_subgraph")


def classify_failed_gates(failed_gates: list[Any]) -> str:
    """Classify mixed gate failure records into a retry target subgraph."""
    gate_ids = [_extract_gate_id(gate) for gate in failed_gates]
    return classify_failure([gate_id for gate_id in gate_ids if gate_id is not None])


def classify_failures_by_gate_names(failed_gate_names: list[str]) -> str:
    """Classify failures using gate-name strings."""
    return classify_failed_gates(failed_gate_names)


def _extract_gate_id(gate: Any) -> int | None:
    if isinstance(gate, dict):
        raw_id = gate.get("gate_id")
        if raw_id is None:
            raw_id = gate.get("id")
        return _coerce_gate_id(raw_id)

    if not isinstance(gate, str):
        return None

    gate_id = _extract_gate_id_from_text(gate)
    if gate_id is not None:
        return gate_id

    normalized = gate.strip()
    for known_id, known_name in GATE_NAMES.items():
        if normalized == known_name:
            return known_id
    return None


def _extract_gate_id_from_text(name: str) -> int | None:
    """Extract gate IDs from labels such as ``Gate 5`` or ``G4-A ...``.

    G4 labels are mapped by the letter after ``G4-``:
    ``G4-A`` → 12 through ``G4-H`` → 19.
    """
    gate_match = re.match(r"^Gate\s+(\d+)\b", name)
    if gate_match:
        return int(gate_match.group(1))
    g4_match = re.match(r"^G4-([A-H])\b", name, flags=re.IGNORECASE)
    if g4_match:
        return 12 + ord(g4_match.group(1).upper()) - ord("A")
    return None


def _coerce_gate_id(raw_id: Any) -> int | None:
    try:
        return int(raw_id)
    except (TypeError, ValueError):
        return None


def get_failure_summary(failed_gate_ids: list[int]) -> dict:
    """Return a structured summary of failures for the report."""
    if not failed_gate_ids:
        return {"total": 0, "retry_target": "none", "gates": []}

    retry_target = classify_failure(failed_gate_ids)
    gates = [
        {
            "gate_id": gid,
            "gate_name": gate_name(gid),
            "retry_subgraph": _GATE_RETRY_MAP.get(gid, "unknown"),
        }
        for gid in sorted(failed_gate_ids)
    ]

    return {
        "total": len(failed_gate_ids),
        "retry_target": retry_target,
        "gates": gates,
    }
