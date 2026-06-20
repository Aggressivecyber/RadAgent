"""Gate Runner — orchestrates base gates and G4 modeling gates.

Runs Gate 0-11 via base_gates, then G4-A to G4-H via g4_modeling_gates.

Status strategy (no dev mode, no partial pass):
  - passed: all critical gates passed; only explicitly non-critical gates may skip
  - failed: any critical gate failed OR any critical gate skipped
  - blocked: external dependency missing when it is a required gate input
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.observability import clear_failure_bundle, record_event, write_failure_bundle
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import STAGE_GATE_VALIDATION

from .schemas import GateSubgraphState

# Gates are critical unless a gate result explicitly sets critical=False.
CRITICAL_GATE_IDS = {6, 7, 8, 9, 10, 11}
VALID_RUN_MODES = {"strict", "test", "acceptance", "production"}


def normalize_run_mode(run_mode: str | None) -> str:
    """Return a supported run mode, rejecting removed dev/partial modes."""
    mode = (run_mode or "strict").strip().lower()
    if mode not in VALID_RUN_MODES:
        raise ValueError(
            f"Unsupported run_mode '{run_mode}'. Use strict/test/acceptance/production."
        )
    return mode


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
    run_mode: str = "strict",
) -> str:
    """Compute validation status from gate results.

    No dev mode. No partial pass. Gates are critical by default.

    Args:
        gate_results: List of gate result dicts with 'status' and 'gate_id'.
        run_mode: "strict" | "test" | "acceptance" | "production"

    Returns:
        "passed", "failed", or "blocked".
    """
    normalize_run_mode(run_mode)

    blocked = [g for g in gate_results if g.get("status") == "blocked"]
    failed = [g for g in gate_results if g.get("status") in ("fail", "block")]
    critical_skipped = [
        g
        for g in gate_results
        if g.get("status") in ("skip", "skipped") and g.get("critical", True) is not False
    ]

    if blocked:
        return "blocked"
    if failed:
        return "failed"

    if critical_skipped:
        return "failed"

    return "passed"


async def finalize_gate_results(state: GateSubgraphState) -> dict[str, Any]:
    """Save gate results and determine validation status."""
    job_id = state.get("job_id", "unknown")
    job_dir = get_job_dir(job_id)
    val_dir = job_dir / STAGE_GATE_VALIDATION
    val_dir.mkdir(parents=True, exist_ok=True)

    gate_results = state.get("gate_results", [])
    run_mode = normalize_run_mode(state.get("run_mode", state.get("execution_mode", "strict")))

    # Save results
    results_path = val_dir / "gate_results.json"
    results_path.write_text(json.dumps(gate_results, indent=2, ensure_ascii=False))

    # Determine status — no partial pass, no dev mode
    status = compute_validation_status(gate_results, run_mode=run_mode)

    failed_gates = [g for g in gate_results if g.get("status") in ("fail", "block", "blocked")]
    skipped_gates = [g for g in gate_results if g.get("status") in ("skip", "skipped")]
    for gate in gate_results:
        gate_status = gate.get("status", "unknown")
        record_event(
            job_id=job_id,
            event_type="gate_runner_gate_result",
            status="passed" if gate_status == "pass" else "failed",
            phase="gate_validation",
            gate_name=str(gate.get("name", gate.get("gate_id", ""))),
            summary=f"Gate {gate.get('gate_id')}: {gate.get('name', '')} -> {gate_status}",
            metrics={
                "gate_id": gate.get("gate_id"),
                "critical": gate.get("critical", True),
                "failed_item_count": len(gate.get("failed_items", [])),
                "warning_count": len(gate.get("warnings", [])),
            },
            artifacts=[{"path": p} for p in gate.get("file_paths", []) if p],
            errors=[str(item) for item in gate.get("failed_items", [])],
            warnings=[str(item) for item in gate.get("warnings", [])],
            details={"message": gate.get("message", ""), "evidence": gate.get("evidence", [])},
        )

    record_event(
        job_id=job_id,
        event_type="gate_runner_final_status",
        status="passed" if status == "passed" else "failed",
        phase="gate_validation",
        summary=f"Gate validation {status}",
        metrics={
            "gate_count": len(gate_results),
            "failed_gate_count": len(failed_gates),
            "skipped_gate_count": len(skipped_gates),
        },
        artifacts=[{"path": str(results_path)}],
        errors=[g.get("message", str(g)) for g in failed_gates],
        warnings=[g.get("message", str(g)) for g in skipped_gates],
    )
    if status == "passed":
        clear_failure_bundle(job_id=job_id)
    else:
        write_failure_bundle(
            job_id=job_id,
            status=status,
            phase="gate_validation",
            errors=[g.get("message", str(g)) for g in failed_gates],
            warnings=[g.get("message", str(g)) for g in skipped_gates],
            artifacts=[{"path": str(results_path)}],
            details={
                "failed_gates": failed_gates,
                "skipped_gates": skipped_gates,
            },
        )

    return {
        "gate_results_path": str(results_path),
        "validation_status": status,
        "failed_gates": failed_gates,
        "skipped_gates": skipped_gates,
    }
