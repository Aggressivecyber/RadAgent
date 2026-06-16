#!/usr/bin/env python3
"""Inspect RadAgent job-scoped observability logs."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from agent_core.workspace.paths import STAGE_CODEGEN


def _resolve_job_dir(value: str) -> Path:
    candidate = Path(value)
    if candidate.exists():
        if (candidate / "logs" / "events.jsonl").exists():
            return candidate
        nested_job = _latest_nested_job_dir(candidate)
        if nested_job is not None:
            return nested_job
        return candidate
    from agent_core.workspace.io import get_job_dir

    return get_job_dir(value)


def _latest_nested_job_dir(candidate: Path) -> Path | None:
    jobs_dir = candidate / "jobs"
    if not jobs_dir.is_dir():
        return None
    job_event_paths = list(jobs_dir.glob("*/logs/events.jsonl"))
    if not job_event_paths:
        return None
    latest_events = max(job_event_paths, key=lambda path: path.stat().st_mtime)
    return latest_events.parents[1]


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


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_model_call_transcripts(job_dir: Path) -> list[dict[str, Any]]:
    model_dir = job_dir / "logs" / "model_calls"
    if not model_dir.is_dir():
        return []
    transcripts: list[dict[str, Any]] = []
    for path in sorted(model_dir.glob("*.json")):
        data = _read_json(path)
        if not data:
            continue
        data["_path"] = str(path)
        transcripts.append(data)
    return transcripts


def build_summary(job_dir: Path) -> dict[str, Any]:
    events = _read_events(job_dir)
    active_model_call = _read_json(job_dir / "logs" / "active_model_call.json")
    transcripts = _read_model_call_transcripts(job_dir)
    failed = [e for e in events if e.get("status") in {"failed", "error"}]
    model_calls = [e for e in events if e.get("event_type") == "model_call"]
    model_call_starts = [e for e in events if e.get("event_type") == "model_call_start"]
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
        "active_model_call": active_model_call,
        "final_status_events": final_status_events,
        "failed_event_count": len(failed),
        "failed_events": failed[-20:],
        "recent_model_call_starts": [
            {
                "module_name": e.get("module_name"),
                "phase": e.get("phase"),
                "status": e.get("status"),
                "summary": e.get("summary"),
                "artifacts": e.get("artifacts", []),
            }
            for e in model_call_starts[-5:]
        ],
        "slow_model_calls": [
            {
                "module_name": e.get("module_name"),
                "phase": e.get("phase"),
                "duration_ms": e.get("duration_ms"),
                "status": e.get("status"),
                "errors": e.get("errors", []),
                "artifacts": e.get("artifacts", []),
            }
            for e in slow_model_calls
        ],
        "model_call_summary": _summarize_model_call_transcripts(transcripts),
        "failure_taxonomy": _classify_failures(events),
        "agentic_repair_lessons": _read_json(
            job_dir / STAGE_CODEGEN / "integration" / "agentic_repair_lessons.json"
        ),
        "failure_bundle_path": str(job_dir / "logs" / "failure_bundle.json"),
        "has_failure_bundle": (job_dir / "logs" / "failure_bundle.json").exists(),
    }


def _summarize_model_call_transcripts(
    transcripts: list[dict[str, Any]],
) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    tiers: Counter[str] = Counter()
    max_prompt_by_module: dict[str, int] = {}
    prompt_sizes: list[dict[str, Any]] = []
    slowest: list[dict[str, Any]] = []
    for transcript in transcripts:
        module_name = _model_call_module_name(transcript)
        counts[module_name] += 1
        tier = str(transcript.get("tier") or "")
        if tier:
            tiers[tier] += 1
        prompt_chars = _model_call_prompt_chars(transcript)
        max_prompt_by_module[module_name] = max(
            max_prompt_by_module.get(module_name, 0),
            prompt_chars,
        )
        prompt_sizes.append(
            {
                "module_name": module_name,
                "task": transcript.get("task"),
                "tier": transcript.get("tier"),
                "prompt_chars": prompt_chars,
                "status": transcript.get("status"),
                "path": transcript.get("_path"),
            }
        )
        duration_s = _model_call_duration_s(transcript)
        if duration_s is not None:
            slowest.append(
                {
                    "module_name": module_name,
                    "task": transcript.get("task"),
                    "tier": transcript.get("tier"),
                    "duration_s": round(duration_s, 3),
                    "status": transcript.get("status"),
                    "path": transcript.get("_path"),
                }
            )
    return {
        "total": len(transcripts),
        "counts_by_module": dict(sorted(counts.items())),
        "counts_by_tier": dict(sorted(tiers.items())),
        "max_prompt_chars_by_module": dict(sorted(max_prompt_by_module.items())),
        "largest_prompt_chars": sorted(
            prompt_sizes,
            key=lambda item: int(item.get("prompt_chars") or 0),
            reverse=True,
        )[:10],
        "slowest_calls": sorted(
            slowest,
            key=lambda item: float(item.get("duration_s") or 0.0),
            reverse=True,
        )[:10],
    }


def _model_call_module_name(transcript: dict[str, Any]) -> str:
    metadata = transcript.get("metadata")
    if isinstance(metadata, dict) and metadata.get("module_name"):
        return str(metadata["module_name"])
    path = str(transcript.get("_path") or "")
    if "agentic_repair" in path:
        return "agentic_repair"
    return str(transcript.get("module_name") or "unknown")


def _model_call_prompt_chars(transcript: dict[str, Any]) -> int:
    request = transcript.get("request")
    if not isinstance(request, dict):
        return 0
    total = len(str(request.get("system_prompt") or ""))
    total += len(str(request.get("user_prompt") or ""))
    messages = request.get("messages")
    if isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict):
                total += len(str(message.get("content") or ""))
                if message.get("tool_calls"):
                    total += len(json.dumps(message.get("tool_calls"), ensure_ascii=False))
    return total


def _model_call_duration_s(transcript: dict[str, Any]) -> float | None:
    start = transcript.get("started_at_unix")
    end = transcript.get("updated_at_unix")
    try:
        return float(end) - float(start)
    except (TypeError, ValueError):
        return None


def _classify_failures(events: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, str]]] = {}
    for event in events:
        text = _event_failure_text(event)
        if not text:
            continue
        labels = _failure_labels(text)
        for label in labels:
            counts[label] += 1
            examples.setdefault(label, [])
            if len(examples[label]) < 3:
                examples[label].append(
                    {
                        "event_type": str(event.get("event_type") or ""),
                        "module_name": str(event.get("module_name") or ""),
                        "summary": str(event.get("summary") or "")[:240],
                    }
                )
    return {
        "counts": dict(sorted(counts.items())),
        "examples": examples,
    }


def _event_failure_text(event: dict[str, Any]) -> str:
    if event.get("status") not in {"failed", "error", "fail"} and not event.get("errors"):
        return ""
    parts: list[str] = []
    for key in ("summary", "errors", "warnings", "details"):
        value = event.get(key)
        if value:
            parts.append(json.dumps(value, ensure_ascii=False, default=str))
    return "\n".join(parts)


def _failure_labels(text: str) -> list[str]:
    lowered = text.lower()
    labels: list[str] = []
    if " error:" in lowered or "fatal error:" in lowered or "undefined reference" in lowered:
        labels.append("compile_error")
    if (
        "has not been declared" in lowered
        and any(token.lower() in lowered for token in _GEANT4_TYPE_INCLUDE_HINTS)
    ):
        labels.append("geant4_missing_type_include")
    if "no declaration matches" in lowered or "does not match any" in lowered:
        labels.append("signature_mismatch")
    if "fgeometrycomponents" in lowered and "not declared" in lowered:
        labels.append("geometry_view_phantom_member")
    if "missing output contract files" in lowered:
        labels.append("missing_output_contract")
    if "geometry_view.json" in lowered or "particle_tracks.json" in lowered or "energy_deposits.json" in lowered:
        labels.append("visual_workbench_artifact")
    if "event_table.csv" in lowered or "g4_summary.json" in lowered:
        labels.append("event_summary_contract")
    if "std::length_error" in lowered or "max_size" in lowered:
        labels.append("voxel_grid_allocation")
    if "geomvol1002" in lowered or "geom0003" in lowered or "overlap" in lowered:
        labels.append("geometry_overlap")
    if "placeholder" in lowered and ("event" in lowered or "track" in lowered):
        labels.append("placeholder_event_track_id")
    if not labels:
        labels.append("other")
    return labels


_GEANT4_TYPE_INCLUDE_HINTS = {
    "G4Material": "G4Material.hh",
    "G4VSolid": "G4VSolid.hh",
    "G4ThreeVector": "G4ThreeVector.hh",
    "G4ParticleDefinition": "G4ParticleDefinition.hh",
    "G4ParticleTable": "G4ParticleTable.hh",
    "G4Colour": "G4Colour.hh",
    "G4VisAttributes": "G4VisAttributes.hh",
    "G4RotationMatrix": "G4RotationMatrix.hh",
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

    if summary["active_model_call"]:
        call = summary["active_model_call"]
        print("Current/last model call:")
        print(
            f"  - {call.get('module_name') or '-'} {call.get('task')} "
            f"{call.get('status')} {call.get('model_name')}"
        )
        if call.get("transcript_path"):
            print(f"    transcript: {job_dir / call['transcript_path']}")

    if summary["recent_model_call_starts"]:
        print("Recent model call starts:")
        for call in summary["recent_model_call_starts"]:
            artifact = (call.get("artifacts") or [{}])[0].get("path", "")
            print(
                f"  - {call.get('module_name') or '-'} "
                f"{call.get('phase')} {call.get('status')}"
            )
            if artifact:
                print(f"    transcript: {job_dir / artifact}")

    model_summary = summary.get("model_call_summary", {})
    if model_summary.get("total"):
        print("Model call summary:")
        print(f"  - total: {model_summary['total']}")
        print("  - by module:")
        for name, count in model_summary.get("counts_by_module", {}).items():
            print(f"    {name}: {count}")
        print("  - largest prompts:")
        for call in model_summary.get("largest_prompt_chars", [])[:5]:
            print(
                f"    {call.get('module_name')}: {call.get('prompt_chars')} chars "
                f"{call.get('status')}"
            )
        max_by_module = model_summary.get("max_prompt_chars_by_module", {})
        if max_by_module:
            print("  - max prompt by module:")
            for module_name, prompt_chars in sorted(max_by_module.items()):
                print(f"    {module_name}: {prompt_chars} chars")
        print("  - slowest transcript calls:")
        for call in model_summary.get("slowest_calls", [])[:5]:
            print(
                f"    {call.get('module_name')}: {call.get('duration_s')} s "
                f"{call.get('status')}"
            )

    taxonomy = summary.get("failure_taxonomy", {})
    if taxonomy.get("counts"):
        print("Failure taxonomy:")
        for label, count in taxonomy.get("counts", {}).items():
            print(f"  - {label}: {count}")
    lessons = summary.get("agentic_repair_lessons", {})
    if isinstance(lessons, dict) and lessons.get("lessons"):
        print("Agentic repair lessons:")
        for lesson in lessons.get("lessons", [])[:8]:
            print(
                f"  - {lesson.get('id')}: {lesson.get('prompt_instruction', '')}"
            )

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
            artifact = (call.get("artifacts") or [{}])[0].get("path", "")
            if artifact:
                print(f"    transcript: {job_dir / artifact}")

    if summary["has_failure_bundle"]:
        print(f"Failure bundle: {summary['failure_bundle_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
