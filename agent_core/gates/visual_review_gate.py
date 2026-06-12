"""Gate 21 native Geant4 visual review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_core.gates.base_gates import gate_name

from .schemas import GateSubgraphState

GATE_ID = 21


async def run_visual_review_gate(state: GateSubgraphState) -> dict[str, Any]:
    """Block Geant4 completion until the user approves the visual workbench."""
    gate_results: list[dict[str, Any]] = list(state.get("gate_results", []))
    failed: list[Any] = list(state.get("failed_gates", []))
    task_spec = state.get("task_spec", {})
    code_dir = state.get("generated_code_dir", "")

    if not _requires_g4_visual_review(task_spec, code_dir):
        return {"gate_results": gate_results, "failed_gates": failed}

    run_mode = str(state.get("run_mode") or state.get("execution_mode") or "strict").strip().lower()
    if run_mode == "test":
        gate_results.append(
            {
                "gate_id": GATE_ID,
                "name": gate_name(GATE_ID),
                "status": "pass",
                "checked_items": [
                    {
                        "item": "100-event native G4 visual workbench review",
                        "result": "pass",
                    }
                ],
                "passed_items": ["visual review auto-approved in test mode"],
                "failed_items": [],
                "warnings": ["Visual review auto-approved because run_mode=test."],
                "evidence": ["run_mode=test"],
                "file_paths": [],
                "message": "G4 visual review auto-approved in test mode",
            }
        )
        return {"gate_results": gate_results, "failed_gates": failed}

    visual_status = str(state.get("visual_review_status") or "missing").strip().lower()
    visual_notes = str(state.get("visual_review_notes") or "").strip()
    visual_passed = visual_status == "approved"
    visual_message = (
        "G4 visual review approved"
        if visual_passed
        else (
            "G4 visual review rejected"
            if visual_status == "rejected"
            else "G4 visual review pending; run /workbench 100 and record /visual-approve"
        )
    )
    gate_entry = {
        "gate_id": GATE_ID,
        "name": gate_name(GATE_ID),
        "status": "pass" if visual_passed else "blocked",
        "checked_items": [
            {
                "item": "100-event native G4 visual workbench review",
                "result": "pass" if visual_passed else "blocked",
            }
        ],
        "passed_items": ["visual review approved"] if visual_passed else [],
        "failed_items": [] if visual_passed else [visual_message],
        "warnings": [] if visual_passed else [visual_notes] if visual_notes else [],
        "evidence": [visual_notes] if visual_notes else [],
        "file_paths": [],
        "message": visual_message,
    }
    gate_results.append(gate_entry)
    if not visual_passed:
        failed.append(gate_entry)
    return {"gate_results": gate_results, "failed_gates": failed}


def _requires_g4_visual_review(task_spec: dict[str, Any], code_dir: str) -> bool:
    """Require visual approval for generated Geant4 projects only."""
    if not code_dir:
        return False
    project_dir = Path(code_dir)
    if not project_dir.is_dir() or not (project_dir / "CMakeLists.txt").is_file():
        return False

    scope = task_spec.get("simulation_scope")
    if isinstance(scope, str):
        return scope.strip().lower() == "geant4"
    if isinstance(scope, list):
        return any(str(item).strip().lower() == "geant4" for item in scope)
    return False
