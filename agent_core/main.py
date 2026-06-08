"""RadAgent main entry point — subgraph architecture.

Usage:
    python -m agent_core.main "建立包含铝外壳、FR4 PCB、硅传感器的探测器模型"
    python -m agent_core.main --job-id job_xxx --status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from agent_core.config.workspace import get_job_dir, get_workspace_root

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def run_agent(
    query: str,
    job_id: str | None = None,
    execution_mode: str = "dev_no_geant4_env",
) -> dict[str, object]:
    """Run the full RadAgent pipeline for a user query.

    Args:
        query: Natural language simulation request.
        job_id: Optional job ID override.
        execution_mode: "dev_no_geant4_env" or "mvp1_acceptance".

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
    return result


async def check_status(job_id: str) -> dict:
    """Check the status of a previously run job."""
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        return {"status": "not_found", "job_id": job_id}

    status: dict[str, object] = {"status": "found", "job_id": job_id, "artifacts": {}}
    artifacts: dict[str, dict[str, object]] = {}

    checks = {
        "request": "00_request/user_query.md",
        "context": "01_context/evidence_map.json",
        "task_spec": "02_task_spec/task_spec.json",
        "model_ir": "03_model_ir/g4_model_ir.json",
        "gate_results": "09_validation/gate_results.json",
        "report": "10_report/final_report.md",
    }

    for name, rel_path in checks.items():
        full_path = job_dir / rel_path
        artifacts[name] = {
            "exists": full_path.exists(),
            "path": str(full_path),
        }
    status["artifacts"] = artifacts

    gate_file = job_dir / "09_validation" / "gate_results.json"
    if gate_file.exists():
        gates = json.loads(gate_file.read_text())
        passed = sum(1 for g in gates if g.get("passed"))
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
        choices=["dev_no_geant4_env", "mvp1_acceptance"],
        default="dev_no_geant4_env",
        help="Execution mode",
    )

    args = parser.parse_args()

    if args.interactive:
        from agent_core.repl import RadAgentREPL

        repl = RadAgentREPL(execution_mode=args.mode)
        asyncio.run(repl.run())
        return

    if args.list_jobs:
        jobs_dir = get_workspace_root() / "jobs"
        if jobs_dir.exists():
            for job in sorted(jobs_dir.iterdir()):
                if job.is_dir():
                    report = job / "10_report" / "final_report.md"
                    status_marker = "DONE" if report.exists() else "WIP"
                    print(f"  [{status_marker}] {job.name}")
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
