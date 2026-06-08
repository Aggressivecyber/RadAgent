#!/usr/bin/env python3
"""Production pipeline entry point for RadAgent.

Usage:
    python scripts/run_pipeline.py --query "Simulate..."
    python scripts/run_pipeline.py --query-file query.txt
    python scripts/run_pipeline.py --run-mode dev --query "..."
    python scripts/run_pipeline.py --run-mode dev --query "你好"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.graph.main_graph import compile_main_graph  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RadAgent production pipeline")
    parser.add_argument("--job-id", default="", help="Job identifier (auto-generated if empty)")
    parser.add_argument("--run-mode", default="dev", choices=["dev", "acceptance", "production"])
    parser.add_argument("--query", help="User query string")
    parser.add_argument("--query-file", help="Path to file containing user query")
    parser.add_argument("--human-response-file", help="Path to human response JSON (for dev mode)")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # Load query
    if args.query:
        query = args.query
    elif args.query_file:
        query = Path(args.query_file).read_text(encoding="utf-8").strip()
    else:
        print("Error: --query or --query-file required", file=sys.stderr)
        sys.exit(1)

    # Load optional human response
    raw_human_response = {}
    if args.human_response_file:
        raw_human_response = json.loads(Path(args.human_response_file).read_text(encoding="utf-8"))

    # Build initial state
    state = {
        "job_id": args.job_id,
        "user_query": query,
        "run_mode": args.run_mode,
        "raw_human_response": raw_human_response,
        "errors": [],
    }

    # Run main graph using compiled graph (not build_main_graph().invoke())
    graph = compile_main_graph()
    result = await graph.ainvoke(state)

    # Output result as JSON for programmatic consumption
    output = {
        "intent": result.get("intent", "unknown"),
        "response_status": result.get("response_status", ""),
        "pipeline_terminated": result.get("pipeline_terminated", False),
        "job_id": result.get("job_id", ""),
        "validation_status": result.get("validation_status", ""),
        "final_report_path": result.get("final_report_path", ""),
    }

    # Print human-readable summary
    print(f"\nIntent: {output['intent']}")
    if output["response_status"]:
        print(f"Response: {result.get('response_text', '')}")
    if output["job_id"]:
        print(f"Job: {output['job_id']}")
    if output["validation_status"]:
        print(f"Status: {output['validation_status']}")
    if output["final_report_path"]:
        print(f"Report: {output['final_report_path']}")
    if result.get("errors"):
        print(f"Errors: {result['errors']}")

    # Also output machine-readable JSON to stderr
    print(json.dumps(output, ensure_ascii=False), file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
