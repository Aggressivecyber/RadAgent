#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from agent_core.workspace.paths import STAGE_CODEGEN, STAGE_GATE_VALIDATION


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _percentile(values: list[float], percentile: float, *, nearest_rank: bool = False) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if nearest_rank:
        rank = max(1, math.ceil(len(ordered) * percentile))
        return round(ordered[min(rank - 1, len(ordered) - 1)], 3)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 3)


def _distribution(values: list[int]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "values": ordered,
        "count": len(ordered),
        "min": ordered[0] if ordered else 0,
        "max": ordered[-1] if ordered else 0,
        "p50": _percentile([float(value) for value in ordered], 0.50) if ordered else 0.0,
    }


def _latency_s(transcript: dict[str, Any]) -> float:
    result = _as_dict(transcript.get("result"))
    latency_ms = result.get("latency_ms")
    if isinstance(latency_ms, int | float) and latency_ms >= 0:
        return round(float(latency_ms) / 1000.0, 3)
    started = transcript.get("started_at_unix")
    updated = transcript.get("updated_at_unix")
    if isinstance(started, int | float) and isinstance(updated, int | float) and updated >= started:
        return round(float(updated - started), 3)
    return 0.0


def _usage_total_tokens(transcript: dict[str, Any]) -> int:
    usage = _as_dict(_as_dict(transcript.get("result")).get("usage"))
    total = usage.get("total_tokens")
    if isinstance(total, int | float):
        return int(total)
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return _safe_int(prompt) + _safe_int(completion)


def _safe_int(value: Any) -> int:
    if isinstance(value, int | float):
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


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


def _critical_gate_failed(gate: dict[str, Any]) -> bool:
    status = str(gate.get("status") or "").strip().lower()
    critical = gate.get("critical", True)
    return critical is not False and status not in {"pass", "passed", "success", "skipped"}


def _load_manifest(path: str | Path) -> list[dict[str, Any]]:
    payload = _read_json(Path(path))
    if isinstance(payload, list):
        cases = payload
    else:
        cases = _as_list(_as_dict(payload).get("cases"))
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(cases):
        case = _as_dict(item)
        case_id = str(case.get("case_id") or case.get("id") or f"case_{index + 1}")
        job_id = str(case.get("job_id") or case.get("job") or "")
        normalized.append({**case, "case_id": case_id, "job_id": job_id})
    return normalized


def _model_call_summary(job_dir: Path) -> dict[str, Any]:
    transcripts = [
        payload
        for path in sorted((job_dir / "logs" / "model_calls").glob("*.json"))
        if isinstance((payload := _read_json(path)), dict)
    ]
    latencies = [_latency_s(item) for item in transcripts]
    return {
        "total_calls": len(transcripts),
        "total_tokens": sum(_usage_total_tokens(item) for item in transcripts),
        "latency_values_s": latencies,
        "latency_s": {
            "count": len(latencies),
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95, nearest_rank=True),
            "max": round(max(latencies), 3) if latencies else 0.0,
            "mean": round(mean(latencies), 3) if latencies else 0.0,
        },
    }


def _case_metrics(workspace: Path, case: dict[str, Any]) -> dict[str, Any]:
    job_id = str(case.get("job_id") or "")
    job_dir = workspace / "jobs" / job_id if job_id else Path()
    gates_payload = _read_json(job_dir / STAGE_GATE_VALIDATION / "gate_results.json")
    gates = _as_list(_as_dict(gates_payload).get("results")) if isinstance(gates_payload, dict) else _as_list(gates_payload)
    final_gate_passed = bool(gates) and not any(
        _critical_gate_failed(gate) for gate in gates if isinstance(gate, dict)
    )

    report = _as_dict(
        _read_json(job_dir / STAGE_CODEGEN / "global_integration_agent_report.json")
    )
    agentic = _as_dict(report.get("agentic"))
    tool_audit = _as_list(agentic.get("tool_audit"))
    first_smoke = _first_tool_turn(tool_audit)
    first_passing_smoke = _first_tool_turn(tool_audit, passing=True)
    n_turns = agentic.get("n_turns")

    return {
        "case_id": str(case.get("case_id") or ""),
        "job_id": job_id,
        "job_exists": job_dir.is_dir(),
        "final_gate_passed": final_gate_passed,
        "failed_critical_gates": [
            str(gate.get("name") or gate.get("gate_id") or "gate")
            for gate in gates
            if isinstance(gate, dict) and _critical_gate_failed(gate)
        ],
        "agentic_stop_reason": str(agentic.get("stop_reason") or "unknown"),
        "agentic_turns": int(n_turns) if isinstance(n_turns, int | float) else 0,
        "turn_to_first_smoke": first_smoke,
        "turn_to_first_passing_smoke": first_passing_smoke,
        "model_calls": _model_call_summary(job_dir),
    }


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    smoke_turns = [
        int(value)
        for case in cases
        if isinstance((value := case.get("turn_to_first_smoke")), int)
    ]
    passing_smoke_turns = [
        int(value)
        for case in cases
        if isinstance((value := case.get("turn_to_first_passing_smoke")), int)
    ]
    stop_reasons = Counter(str(case.get("agentic_stop_reason") or "unknown") for case in cases)
    all_latencies: list[float] = []
    total_calls = 0
    total_tokens = 0
    for case in cases:
        model_calls = _as_dict(case.get("model_calls"))
        total_calls += int(model_calls.get("total_calls") or 0)
        total_tokens += int(model_calls.get("total_tokens") or 0)
        all_latencies.extend(
            float(value)
            for value in _as_list(model_calls.get("latency_values_s"))
            if isinstance(value, int | float)
        )
    case_count = len(cases)
    passed = sum(1 for case in cases if case.get("final_gate_passed") is True)
    return {
        "case_count": case_count,
        "final_gate_pass_count": passed,
        "final_gate_pass_rate": round(passed / case_count, 4) if case_count else 0.0,
        "agentic_stop_reasons": dict(sorted(stop_reasons.items())),
        "turn_to_first_smoke": _distribution(smoke_turns),
        "turn_to_first_passing_smoke": _distribution(passing_smoke_turns),
        "model_calls": {
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "latency_s": {
                "count": len(all_latencies),
                "p50": _percentile(all_latencies, 0.50),
                "p95": _percentile(all_latencies, 0.95, nearest_rank=True),
                "max": round(max(all_latencies), 3) if all_latencies else 0.0,
                "mean": round(mean(all_latencies), 3) if all_latencies else 0.0,
            },
        },
    }


def collect_golden_set_metrics(
    workspace: str | Path,
    manifest: str | Path,
    *,
    label: str = "",
) -> dict[str, Any]:
    workspace_path = Path(workspace)
    cases = [_case_metrics(workspace_path, case) for case in _load_manifest(manifest)]
    return {
        "label": label or workspace_path.name,
        "workspace": str(workspace_path),
        "manifest": str(manifest),
        "aggregate": _aggregate(cases),
        "cases": cases,
    }


def _pass_map(summary: dict[str, Any]) -> dict[str, bool]:
    return {
        str(case.get("case_id")): bool(case.get("final_gate_passed"))
        for case in _as_list(summary.get("cases"))
    }


def compare_runs(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    baseline_agg = _as_dict(baseline.get("aggregate"))
    current_agg = _as_dict(current.get("aggregate"))
    baseline_model = _as_dict(baseline_agg.get("model_calls"))
    current_model = _as_dict(current_agg.get("model_calls"))
    baseline_latency = _as_dict(baseline_model.get("latency_s"))
    current_latency = _as_dict(current_model.get("latency_s"))
    baseline_cases = _pass_map(baseline)
    current_cases = _pass_map(current)
    case_changes = []
    for case_id in sorted(set(baseline_cases) | set(current_cases)):
        left = baseline_cases.get(case_id)
        right = current_cases.get(case_id)
        if left == right:
            continue
        case_changes.append(
            {
                "case_id": case_id,
                "baseline_passed": left,
                "current_passed": right,
            }
        )
    return {
        "baseline_label": str(baseline.get("label") or "baseline"),
        "current_label": str(current.get("label") or "current"),
        "deltas": {
            "final_gate_pass_rate": round(
                float(current_agg.get("final_gate_pass_rate") or 0.0)
                - float(baseline_agg.get("final_gate_pass_rate") or 0.0),
                4,
            ),
            "model_p50_latency_s": round(
                float(current_latency.get("p50") or 0.0)
                - float(baseline_latency.get("p50") or 0.0),
                3,
            ),
            "total_tokens": int(current_model.get("total_tokens") or 0)
            - int(baseline_model.get("total_tokens") or 0),
        },
        "case_changes": case_changes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and compare RadAgent golden-set metrics.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect metrics for a golden manifest.")
    collect.add_argument("--workspace", default="simulation_workspace")
    collect.add_argument("--manifest", required=True)
    collect.add_argument("--label", default="")
    collect.add_argument("--output", default="")

    compare = subparsers.add_parser("compare", help="Compare two collected metric JSON files.")
    compare.add_argument("baseline")
    compare.add_argument("current")
    compare.add_argument("--output", default="")

    args = parser.parse_args()
    if args.command == "collect":
        payload = collect_golden_set_metrics(args.workspace, args.manifest, label=args.label)
    else:
        payload = compare_runs(_as_dict(_read_json(Path(args.baseline))), _as_dict(_read_json(Path(args.current))))

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
