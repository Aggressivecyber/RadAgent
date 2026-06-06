"""RadAgent main entry point.

Usage:
    python -m agent_core.main "模拟 10 MeV 质子垂直入射 300 微米硅片"
    python -m agent_core.main --job-id job_xxx --status
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Load .env before any other imports
from dotenv import load_dotenv

from agent_core.config.workspace import get_job_dir, get_workspace_root

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Ensure workspace root is accessible
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def run_agent(query: str, job_id: str | None = None) -> dict[str, object]:
    """Run the full RadAgent pipeline for a user query.

    Args:
        query: Natural language simulation request.
        job_id: Optional job ID override.

    Returns:
        Final state dict from the LangGraph execution.
    """
    from agent_core.graph.graph_builder import compile_graph

    # Ensure workspace directories exist
    (get_workspace_root() / "jobs").mkdir(parents=True, exist_ok=True)

    # Build initial state
    initial_state = {
        "user_query": query,
        "job_id": job_id or "",
        "errors": [],
        "retry_count": 0,
        "max_retries_reached": False,
        "execution_mode": "dev_no_geant4_env",
        "skipped_gates": [],
    }

    # Compile and run graph
    graph = compile_graph()
    result: dict[str, object] = await graph.ainvoke(
        initial_state,
        config={"recursion_limit": 50},
    )
    return result


async def check_status(job_id: str) -> dict:
    """Check the status of a previously run job.

    Args:
        job_id: The job ID to check.

    Returns:
        Status dict with job info.
    """
    job_dir = get_job_dir(job_id)
    if not job_dir.exists():
        return {"status": "not_found", "job_id": job_id}

    status: dict[str, object] = {"status": "found", "job_id": job_id, "artifacts": {}}
    artifacts: dict[str, dict[str, object]] = {}

    # Check for each artifact
    checks = {
        "request": "00_request/user_query.md",
        "task_spec": "02_task_spec/task_spec.json",
        "simulation_ir": "03_simulation_ir/simulation_ir.json",
        "rag_context": "01_context/g4_context.json",
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

    # Read gate results if available
    gate_file = job_dir / "09_validation" / "gate_results.json"
    if gate_file.exists():
        gates = json.loads(gate_file.read_text())
        passed = sum(1 for g in gates if g.get("passed"))
        status["gates_summary"] = f"{passed}/{len(gates)} passed"

    return status


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Radiation Simulation Agent (RadAgent)")
    parser.add_argument("query", nargs="?", help="Natural language simulation request")
    parser.add_argument("--job-id", help="Override job ID")
    parser.add_argument("--status", action="store_true", help="Check job status")
    parser.add_argument("--list-jobs", action="store_true", help="List all jobs")

    args = parser.parse_args()

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
    print()

    result = asyncio.run(run_agent(args.query, args.job_id))

    job_id = result.get("job_id", "unknown")
    report = result.get("final_report", "")

    print(f"Job completed: {job_id}")
    report_path = get_job_dir(job_id) / "10_report" / "final_report.md"
    print(f"Report saved to: {report_path}")
    print()

    if report:
        # Print last 30 lines of report as summary
        report_lines = report.split("\n")
        if len(report_lines) > 30:
            print("... (showing last 30 lines)")
            report_lines = report_lines[-30:]
        print("\n".join(report_lines))

    # Print gate summary
    gate_results = result.get("gate_results", [])
    if gate_results:
        passed = sum(1 for g in gate_results if g.get("passed"))
        print(f"\nGate Summary: {passed}/{len(gate_results)} passed")


if __name__ == "__main__":
    main()
