"""RadAgent main entry point — subgraph architecture.

Usage:
    python -m agent_core.main "建立包含铝外壳、FR4 PCB、硅传感器的探测器模型"
    python -m agent_core.main --job-id job_xxx --status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_core.pipeline import PIPELINE_PHASES
from agent_core.workspace.io import get_job_dir, get_workspace_root
from agent_core.workspace.paths import (
    STAGE_CONTEXT,
    STAGE_GATE_VALIDATION,
    STAGE_INPUT,
    STAGE_MODEL_IR,
    STAGE_REPORT,
    STAGE_TASK_PLAN,
)

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def run_agent(
    query: str,
    job_id: str | None = None,
    execution_mode: str = "strict",
) -> dict[str, object]:
    """Run the full RadAgent pipeline for a user query.

    Args:
        query: Natural language simulation request.
        job_id: Optional job ID override.
        execution_mode: "strict", "test", "acceptance", or "production".

    Returns:
        Final state dict from the LangGraph execution.
    """
    from agent_core.graph.main_graph import compile_main_graph

    # Ensure workspace directories exist
    (get_workspace_root() / "jobs").mkdir(parents=True, exist_ok=True)

    # Build initial state
    initial_state: dict[str, object] = {
        "user_query": query,
        "job_id": job_id or "",
        "errors": [],
        "retry_count": 0,
        "max_retries_reached": False,
        "execution_mode": execution_mode,
        "skipped_gates": [],
    }

    # Compile and run main graph
    graph = compile_main_graph()
    result: dict[str, object] = await graph.ainvoke(
        initial_state,
        config={"recursion_limit": 50},
    )
    _persist_run_result(result)
    return result


def _persist_run_result(result: dict[str, object]) -> None:
    """Persist one-shot CLI run state for later listing/resume."""
    job_id = str(result.get("job_id", ""))
    if not job_id:
        return
    try:
        from agent_core.storage import RadAgentStore

        store = RadAgentStore()
        current_node = str(result.get("current_node", ""))
        status = "completed" if result.get("final_report_path") else "failed"
        if result.get("errors"):
            status = "failed"
        phase_idx = len(PIPELINE_PHASES) if status == "completed" else 0
        store.save_state_snapshot(
            job_id=job_id,
            state=dict(result),
            completed_phases=list(PIPELINE_PHASES[:phase_idx]),
            phase=current_node,
            current_phase_idx=phase_idx,
            status=status,
        )
        for key, value in result.items():
            if not isinstance(value, str) or not value:
                continue
            if not (key.endswith("_path") or key.endswith("_dir")):
                continue
            path = Path(value)
            if path.exists():
                stage = path.parent.name if path.is_file() else path.name
                store.record_artifact(job_id=job_id, path=str(path), stage=stage, kind=key)
    except Exception as exc:
        logger.warning("Failed to persist CLI run result for job %s: %s", job_id, exc)


async def check_status(job_id: str) -> dict:
    """Check the status of a previously run job."""
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        return {"status": "not_found", "job_id": job_id}

    status: dict[str, object] = {"status": "found", "job_id": job_id, "artifacts": {}}
    artifacts: dict[str, dict[str, object]] = {}

    checks = {
        "request": f"{STAGE_INPUT}/user_query.md",
        "context": f"{STAGE_CONTEXT}/evidence_map.json",
        "task_spec": f"{STAGE_TASK_PLAN}/task_spec.json",
        "model_ir": f"{STAGE_MODEL_IR}/g4_model_ir.json",
        "gate_results": f"{STAGE_GATE_VALIDATION}/gate_results.json",
        "report": f"{STAGE_REPORT}/final_report.md",
    }

    for name, rel_path in checks.items():
        full_path = job_dir / rel_path
        artifacts[name] = {
            "exists": full_path.exists(),
            "path": str(full_path),
        }
    status["artifacts"] = artifacts

    gate_file = job_dir / STAGE_GATE_VALIDATION / "gate_results.json"
    if gate_file.exists():
        gates = json.loads(gate_file.read_text())
        passed = sum(1 for g in gates if g.get("status") == "pass" or g.get("passed") is True)
        status["gates_summary"] = f"{passed}/{len(gates)} passed"

    return status


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="RadAgent — Geant4 Complex Modeling Agent")
    parser.add_argument("query", nargs="?", help="Natural language simulation request")
    parser.add_argument("--job-id", help="Override job ID")
    parser.add_argument("--status", action="store_true", help="Check job status")
    parser.add_argument("--list-jobs", action="store_true", help="List all jobs")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="Launch interactive REPL mode",
    )
    parser.add_argument(
        "--mode",
        choices=["strict", "test", "acceptance", "production"],
        default="strict",
        help="Execution mode",
    )

    args = parser.parse_args()

    if args.interactive:
        from agent_core.repl import RadAgentREPL

        repl = RadAgentREPL(execution_mode=args.mode)
        asyncio.run(repl.run())
        return

    if args.list_jobs:
        from agent_core.storage import RadAgentStore

        store = RadAgentStore()
        store.import_existing_jobs()
        jobs = store.list_jobs()
        if jobs:
            for job in jobs:
                status_marker = "DONE" if job["status"] == "completed" else job["status"].upper()
                print(f"  [{status_marker}] {job['job_id']} ({job['project_slug']})")
        else:
            print("No jobs found.")
        return

    if args.status and args.job_id:
        result = asyncio.run(check_status(args.job_id))
        print(json.dumps(result, indent=2))
        return

    if not args.query:
        parser.print_help()
        return

    print("RadAgent: Processing request...")
    print(f"  Query: {args.query}")
    print(f"  Mode: {args.mode}")
    print()

    result = asyncio.run(run_agent(args.query, args.job_id, args.mode))

    job_id = result.get("job_id", "unknown")
    print(f"Job completed: {job_id}")
    report_path = result.get("final_report_path", "")
    if report_path:
        print(f"Report saved to: {report_path}")
    print()

    # Print verification status
    verified = result.get("verified", False)
    print(f"Verified: {verified}")
    termination = result.get("termination_reason", "")
    if termination:
        print(f"Termination: {termination}")


if __name__ == "__main__":
    main()
