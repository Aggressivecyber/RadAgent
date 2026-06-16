#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from agent_core.workspace.paths import STAGE_CODEGEN


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _percentile(values: list[float], percentile: float, *, method: str = "linear") -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if method == "nearest_rank":
        rank = max(1, math.ceil(len(ordered) * percentile))
        return round(ordered[min(rank - 1, len(ordered) - 1)], 3)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def _latency_s(transcript: dict[str, Any]) -> float:
    result = transcript.get("result") if isinstance(transcript.get("result"), dict) else {}
    latency_ms = result.get("latency_ms")
    if isinstance(latency_ms, int | float) and latency_ms >= 0:
        return round(float(latency_ms) / 1000.0, 3)
    started = transcript.get("started_at_unix")
    updated = transcript.get("updated_at_unix")
    if isinstance(started, int | float) and isinstance(updated, int | float) and updated >= started:
        return round(float(updated - started), 3)
    return 0.0


def _module_name(transcript: dict[str, Any]) -> str:
    metadata = transcript.get("metadata") if isinstance(transcript.get("metadata"), dict) else {}
    return str(metadata.get("module_name") or "unknown")


def _task_name(transcript: dict[str, Any]) -> str:
    return str(transcript.get("task") or "unknown")


def _has_error(transcript: dict[str, Any]) -> bool:
    result = transcript.get("result") if isinstance(transcript.get("result"), dict) else {}
    return bool(result.get("error") or str(transcript.get("status", "")).lower() in {"failed", "error"})


def _summarize_group(transcripts: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [_latency_s(item) for item in transcripts]
    return {
        "count": len(transcripts),
        "errors": sum(1 for item in transcripts if _has_error(item)),
        "p50_s": _percentile(latencies, 0.50),
        "p95_s": _percentile(latencies, 0.95, method="nearest_rank"),
        "max_s": round(max(latencies), 3) if latencies else 0.0,
        "mean_s": round(mean(latencies), 3) if latencies else 0.0,
    }


def _collect_model_calls(workspace: Path) -> dict[str, Any]:
    transcripts = [
        payload
        for path in sorted(workspace.glob("jobs/*/logs/model_calls/*.json"))
        if (payload := _read_json(path))
    ]
    by_task: dict[str, list[dict[str, Any]]] = {}
    by_module: dict[str, list[dict[str, Any]]] = {}
    for transcript in transcripts:
        by_task.setdefault(_task_name(transcript), []).append(transcript)
        by_module.setdefault(_module_name(transcript), []).append(transcript)
    return {
        "total": len(transcripts),
        "by_task": {key: _summarize_group(value) for key, value in sorted(by_task.items())},
        "by_module": {key: _summarize_group(value) for key, value in sorted(by_module.items())},
    }


def _first_tool_turn(tool_audit: list[Any], *, passing: bool | None = None) -> int | None:
    for entry in tool_audit:
        if not isinstance(entry, dict) or entry.get("name") != "run_smoke":
            continue
        if passing is not None and bool(entry.get("ok")) is not passing:
            continue
        turn = entry.get("turn")
        if isinstance(turn, int | float):
            return int(turn)
    return None


def _distribution(values: list[int]) -> dict[str, Any]:
    return {
        "values": values,
        "count": len(values),
        "min": min(values) if values else 0,
        "max": max(values) if values else 0,
        "p50": _percentile([float(value) for value in values], 0.50) if values else 0.0,
    }


def _collect_agentic(workspace: Path) -> dict[str, Any]:
    stop_reasons: Counter[str] = Counter()
    turns: list[int] = []
    first_smoke: list[int] = []
    first_passing_smoke: list[int] = []
    for path in sorted(
        workspace.glob(f"jobs/*/{STAGE_CODEGEN}/global_integration_agent_report.json")
    ):
        report = _read_json(path)
        agentic = report.get("agentic") if isinstance(report.get("agentic"), dict) else {}
        stop_reason = str(agentic.get("stop_reason") or "unknown")
        stop_reasons[stop_reason] += 1
        n_turns = agentic.get("n_turns")
        if isinstance(n_turns, int | float):
            turns.append(int(n_turns))
        tool_audit = agentic.get("tool_audit") if isinstance(agentic.get("tool_audit"), list) else []
        smoke_turn = _first_tool_turn(tool_audit)
        if smoke_turn is not None:
            first_smoke.append(smoke_turn)
        passing_turn = _first_tool_turn(tool_audit, passing=True)
        if passing_turn is not None:
            first_passing_smoke.append(passing_turn)
    return {
        "stop_reasons": dict(sorted(stop_reasons.items())),
        "turns": _distribution(turns),
        "turn_to_first_smoke": _distribution(first_smoke),
        "turn_to_first_passing_smoke": _distribution(first_passing_smoke),
    }


def collect_metrics(workspace: str | Path) -> dict[str, Any]:
    root = Path(workspace)
    return {
        "workspace": str(root),
        "model_calls": _collect_model_calls(root),
        "agentic": _collect_agentic(root),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate RadAgent model-call and agentic repair metrics.")
    parser.add_argument("workspace", nargs="?", default="simulation_workspace")
    args = parser.parse_args()
    print(json.dumps(collect_metrics(args.workspace), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
