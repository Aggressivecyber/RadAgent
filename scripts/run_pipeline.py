#!/usr/bin/env python3
"""Production pipeline entry point for RadAgent.

Usage:
    python scripts/run_pipeline.py --job-id JOB_ID --query "Simulate..."
    python scripts/run_pipeline.py --job-id JOB_ID --query-file query.txt
    python scripts/run_pipeline.py --job-id JOB_ID --run-mode dev --query "..."
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_core.graph.main_graph import build_main_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RadAgent production pipeline")
    parser.add_argument("--job-id", required=True, help="Unique job identifier")
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
        raw_human_response = json.loads(
            Path(args.human_response_file).read_text(encoding="utf-8")
        )

    # Build initial state
    state = {
        "job_id": args.job_id,
        "user_query": query,
        "run_mode": args.run_mode,
        "raw_human_response": raw_human_response,
        "errors": [],
    }

    # Run main graph
    graph = build_main_graph()
    result = graph.invoke(state)

    # Output
    print(f"\nJob: {result.get('job_id', args.job_id)}")
    print(f"Status: {result.get('validation_status', 'UNKNOWN')}")
    print(f"Report: {result.get('final_report_path', 'N/A')}")
    if result.get('errors'):
        print(f"Errors: {result['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
