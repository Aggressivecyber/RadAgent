#!/usr/bin/env python3
"""Inspect RadAgent job-scoped observability logs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _resolve_job_dir(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        return candidate
    from agent_core.config.workspace import get_job_dir

    return get_job_dir(value)


def _read_events(job_dir: Path) -> list[dict[str, Any]]:
    path = job_dir / "logs" / "events.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def build_summary(job_dir: Path) -> dict[str, Any]:
    events = _read_events(job_dir)
    failed = [e for e in events if e.get("status") in {"failed", "error"}]
    model_calls = [e for e in events if e.get("event_type") == "model_call"]
    slow_model_calls = sorted(
        model_calls,
        key=lambda e: float(e.get("duration_ms") or 0.0),
        reverse=True,
    )[:10]

    final_status_events = [
        e
        for e in events
        if e.get("event_type") in {"g4_codegen_persist", "gate_runner_final_status"}
    ]

    return {
        "job_dir": str(job_dir),
        "event_count": len(events),
        "event_types": dict(Counter(e.get("event_type", "unknown") for e in events)),
        "final_status_events": final_status_events,
        "failed_event_count": len(failed),
        "failed_events": failed[-20:],
        "slow_model_calls": [
            {
                "module_name": e.get("module_name"),
                "phase": e.get("phase"),
                "duration_ms": e.get("duration_ms"),
                "status": e.get("status"),
                "errors": e.get("errors", []),
            }
            for e in slow_model_calls
        ],
        "failure_bundle_path": str(job_dir / "logs" / "failure_bundle.json"),
        "has_failure_bundle": (job_dir / "logs" / "failure_bundle.json").exists(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", help="Job id or path to simulation_workspace/jobs/<job_id>")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    job_dir = _resolve_job_dir(args.job)
    summary = build_summary(job_dir)

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print(f"Job: {summary['job_dir']}")
    print(f"Events: {summary['event_count']}")
    print(f"Failed events: {summary['failed_event_count']}")
    print("Event types:")
    for name, count in sorted(summary["event_types"].items()):
        print(f"  - {name}: {count}")

    if summary["final_status_events"]:
        print("Final statuses:")
        for event in summary["final_status_events"]:
            print(f"  - {event.get('event_type')}: {event.get('status')} {event.get('summary')}")

    if summary["failed_events"]:
        print("Recent failures:")
        for event in summary["failed_events"][-10:]:
            where = event.get("module_name") or event.get("gate_name") or event.get("layer")
            print(f"  - {event.get('event_type')} {where}: {event.get('summary')}")
            for error in event.get("errors", [])[:3]:
                print(f"      {error}")

    if summary["slow_model_calls"]:
        print("Slow model calls:")
        for call in summary["slow_model_calls"][:5]:
            print(
                f"  - {call.get('module_name') or '-'} "
                f"{call.get('phase')} {call.get('duration_ms')} ms {call.get('status')}"
            )

    if summary["has_failure_bundle"]:
        print(f"Failure bundle: {summary['failure_bundle_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
