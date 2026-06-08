"""Gate Runner — orchestrates base gates and G4 modeling gates.

Runs Gate 0-11 via base_gates, then G4-A to G4-G via g4_modeling_gates.

Status strategy:
  - VERIFIED: all gates passed, no failures, no skips
  - PARTIAL: no failures, some non-critical gates skipped (dev mode)
  - FAILED: any gate failed, OR critical gates skipped in acceptance mode
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir

from .schemas import GateSubgraphState

# Critical gates — skipping these in acceptance mode means FAILED
CRITICAL_GATE_IDS = {6, 7, 8, 9, 10, 11}


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


def compute_validation_status(
    gate_results: list[dict[str, Any]],
    execution_mode: str | None = None,
    run_mode: str = "dev",
) -> str:
    """Compute validation status from gate results.

    Args:
        gate_results: List of gate result dicts with 'status' and 'gate_id'.
        execution_mode: Deprecated - use run_mode instead. "dev" or "mvp1_acceptance".
        run_mode: "dev" | "acceptance" | "production" (preferred parameter).

    Returns:
        "VERIFIED", "PARTIAL", or "FAILED".
    """
    # Backward compat: use execution_mode if run_mode not provided
    if execution_mode and run_mode == "dev":
        if execution_mode == "mvp1_acceptance":
            run_mode = "acceptance"

    failed = [g for g in gate_results if g.get("status") == "fail"]
    # Handle both 'skip' and 'skipped' for backward compatibility
    skipped = [g for g in gate_results if g.get("status") in ("skip", "skipped")]

    if failed:
        return "FAILED"

    skipped_ids = {int(g["gate_id"]) for g in skipped if str(g.get("gate_id", "")).isdigit()}
    critical_skipped = skipped_ids & CRITICAL_GATE_IDS

    # Critical gates skipped:
    # - dev: allow -> PARTIAL
    # - acceptance: block -> FAILED
    # - production: block -> FAILED
    if critical_skipped:
        if run_mode in {"dev"}:
            return "PARTIAL"
        else:  # acceptance, production
            return "FAILED"

    if skipped:
        if run_mode == "dev":
            return "PARTIAL"
        elif run_mode == "acceptance":
            return "PARTIAL"
        else:  # production
            return "FAILED"

    return "VERIFIED"


async def finalize_gate_results(state: GateSubgraphState) -> dict[str, Any]:
    """Save gate results and determine validation status."""
    job_id = state.get("job_id", "unknown")
    job_dir = get_job_dir(job_id)
    val_dir = job_dir / "08_gate_validation"
    val_dir.mkdir(parents=True, exist_ok=True)

    gate_results = state.get("gate_results", [])
    # Prefer run_mode, fall back to execution_mode for backward compatibility
    run_mode = state.get("run_mode", state.get("execution_mode", "dev"))
    # Normalize legacy execution_mode values to run_mode
    if run_mode == "mvp1_acceptance":
        run_mode = "acceptance"
    elif run_mode == "dev_no_geant4_env":
        run_mode = "dev"

    # Save results
    results_path = val_dir / "gate_results.json"
    results_path.write_text(json.dumps(gate_results, indent=2, ensure_ascii=False))

    # Determine status using the new strategy
    status = compute_validation_status(gate_results, run_mode=run_mode)

    failed_gates = [g for g in gate_results if g.get("status") == "fail"]
    # Handle both 'skip' and 'skipped' for backward compatibility
    skipped_gates = [g for g in gate_results if g.get("status") in ("skip", "skipped")]

    return {
        "gate_results_path": str(results_path),
        "validation_status": status,
        "failed_gates": failed_gates,
        "skipped_gates": skipped_gates,
    }
