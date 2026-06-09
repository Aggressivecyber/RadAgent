"""Failure Classifier — classifies gate failures for retry routing.

Maps failed gate IDs to the subgraph that should handle the retry:
- Gate 0-1 → context_subgraph
- Gate 2 → g4_modeling_subgraph
- Gate 3-6 → g4_codegen_subgraph / patch_subgraph
- Gate 7-11 → g4_codegen_subgraph for runtime/code contract repair
- G4-A to G4-C (12-14) → g4_modeling_subgraph
- G4-D to G4-G (15-18) → g4_codegen_subgraph
"""

from __future__ import annotations

from .base_gates import gate_name

# Gate ID → target subgraph for retry
_GATE_RETRY_MAP: dict[int, str] = {
    0: "context_subgraph",
    1: "context_subgraph",
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
    15: "g4_codegen_subgraph",
    16: "g4_modeling_subgraph",
    17: "g4_codegen_subgraph",
    18: "g4_codegen_subgraph",
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


def classify_failures_by_gate_names(failed_gate_names: list[str]) -> str:
    """Classify failures using gate name strings.

    Extracts gate IDs from names like "Gate 5", "G4-A Model Completeness", etc.
    """
    gate_ids: list[int] = []

    for name in failed_gate_names:
        # Try "Gate N" pattern
        if name.startswith("Gate "):
            try:
                gate_ids.append(int(name.split()[-1]))
            except ValueError:
                pass
        # Try "G4-X" pattern
        elif name.startswith("G4-"):
            letter = name[3]
            gate_ids.append(12 + ord(letter.upper()) - ord("A"))

    return classify_failure(gate_ids)


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
