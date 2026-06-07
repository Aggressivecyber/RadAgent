"""Gate Runner — orchestrates base gates and G4 modeling gates.

Runs Gate 0-11 via base_gates, then G4-A to G4-G via g4_modeling_gates.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir

from .schemas import GateSubgraphState


async def load_gate_inputs(state: GateSubgraphState) -> dict[str, Any]:
    """Load all required data from file paths."""
    ir_path = state.get("g4_model_ir_path", "")
    ts_path = state.get("task_spec_path", "")

    model_ir: dict[str, Any] = {}
    task_spec: dict[str, Any] = {}

    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text())
    if ts_path and Path(ts_path).exists():
        task_spec = json.loads(Path(ts_path).read_text())

    return {
        "g4_model_ir": model_ir,
        "task_spec": task_spec,
        "gate_results": [],
        "skipped_gates": [],
        "failed_gates": [],
        "errors": [],
    }


async def finalize_gate_results(state: GateSubgraphState) -> dict[str, Any]:
    """Save gate results and determine validation status."""
    job_id = state.get("job_id", "unknown")
    job_dir = get_job_dir(job_id)
    val_dir = job_dir / "09_validation"
    val_dir.mkdir(parents=True, exist_ok=True)

    gate_results = state.get("gate_results", [])
    failed_gates = state.get("failed_gates", [])
    skipped = state.get("skipped_gates", [])

    # Save results
    results_path = val_dir / "gate_results.json"
    results_path.write_text(json.dumps(gate_results, indent=2, ensure_ascii=False))

    # Determine status
    if not failed_gates:
        status = "VERIFIED"
    elif len(failed_gates) <= 2:
        status = "PARTIAL"
    else:
        status = "FAILED"

    return {
        "gate_results_path": str(results_path),
        "validation_status": status,
        "failed_gates": failed_gates,
        "skipped_gates": skipped,
    }
