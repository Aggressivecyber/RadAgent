from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_benchmark_module() -> Any:
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "golden_set_benchmark.py"
    spec = importlib.util.spec_from_file_location("golden_set_benchmark", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_collect_golden_set_metrics_reports_case_success_and_costs(tmp_path: Path) -> None:
    benchmark = _load_benchmark_module()
    workspace = tmp_path / "workspace"
    manifest = tmp_path / "golden.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {"case_id": "shielding", "job_id": "job_pass"},
                    {"case_id": "detector", "job_id": "job_fail"},
                ]
            }
        ),
        encoding="utf-8",
    )

    _write_json(
        workspace / "jobs" / "job_pass" / "07_gate_validation" / "gate_results.json",
        [{"name": "Gate", "status": "pass", "critical": True}],
    )
    _write_json(
        workspace / "jobs" / "job_pass" / "05_codegen" / "global_integration_agent_report.json",
        {
            "agentic": {
                "stop_reason": "stop_hook",
                "n_turns": 8,
                "tool_audit": [
                    {"turn": 2, "name": "run_smoke", "ok": False},
                    {"turn": 5, "name": "run_smoke", "ok": True},
                ],
            }
        },
    )
    _write_json(
        workspace / "jobs" / "job_pass" / "logs" / "model_calls" / "a.json",
        {
            "task": "codegen",
            "result": {
                "latency_ms": 11_000,
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        },
    )
    _write_json(
        workspace / "jobs" / "job_pass" / "logs" / "model_calls" / "a2.json",
        {
            "task": "codegen",
            "result": {
                "latency_ms": 3_000,
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        },
    )

    _write_json(
        workspace / "jobs" / "job_fail" / "07_gate_validation" / "gate_results.json",
        [{"name": "Gate", "status": "fail", "critical": True}],
    )
    _write_json(
        workspace / "jobs" / "job_fail" / "05_codegen" / "global_integration_agent_report.json",
        {
            "agentic": {
                "stop_reason": "max_turns",
                "n_turns": 12,
                "tool_audit": [{"turn": 6, "name": "run_smoke", "ok": False}],
            }
        },
    )
    _write_json(
        workspace / "jobs" / "job_fail" / "logs" / "model_calls" / "b.json",
        {
            "task": "codegen",
            "started_at_unix": 10.0,
            "updated_at_unix": 18.0,
            "result": {"usage": {"total_tokens": 20}},
        },
    )

    summary = benchmark.collect_golden_set_metrics(workspace, manifest, label="mimo-baseline")

    assert summary["label"] == "mimo-baseline"
    assert summary["aggregate"]["case_count"] == 2
    assert summary["aggregate"]["final_gate_pass_rate"] == 0.5
    assert summary["aggregate"]["agentic_stop_reasons"] == {"max_turns": 1, "stop_hook": 1}
    assert summary["aggregate"]["turn_to_first_smoke"]["values"] == [2, 6]
    assert summary["aggregate"]["turn_to_first_passing_smoke"]["values"] == [5]
    assert summary["aggregate"]["model_calls"]["total_calls"] == 3
    assert summary["aggregate"]["model_calls"]["total_tokens"] == 37
    assert summary["aggregate"]["model_calls"]["latency_s"]["p50"] == 8.0
    assert summary["aggregate"]["model_calls"]["latency_s"]["max"] == 11.0
    assert summary["cases"][0]["case_id"] == "shielding"
    assert summary["cases"][0]["final_gate_passed"] is True
    assert summary["cases"][1]["final_gate_passed"] is False


def test_compare_runs_reports_ab_deltas() -> None:
    benchmark = _load_benchmark_module()
    baseline = {
        "label": "mimo",
        "aggregate": {
            "case_count": 2,
            "final_gate_pass_rate": 0.5,
            "model_calls": {"latency_s": {"p50": 20.0}, "total_tokens": 100},
        },
        "cases": [
            {"case_id": "a", "final_gate_passed": False},
            {"case_id": "b", "final_gate_passed": True},
        ],
    }
    current = {
        "label": "optimized",
        "aggregate": {
            "case_count": 2,
            "final_gate_pass_rate": 1.0,
            "model_calls": {"latency_s": {"p50": 8.0}, "total_tokens": 90},
        },
        "cases": [
            {"case_id": "a", "final_gate_passed": True},
            {"case_id": "b", "final_gate_passed": True},
        ],
    }

    comparison = benchmark.compare_runs(baseline, current)

    assert comparison["baseline_label"] == "mimo"
    assert comparison["current_label"] == "optimized"
    assert comparison["deltas"]["final_gate_pass_rate"] == 0.5
    assert comparison["deltas"]["model_p50_latency_s"] == -12.0
    assert comparison["deltas"]["total_tokens"] == -10
    assert comparison["case_changes"] == [
        {"case_id": "a", "baseline_passed": False, "current_passed": True}
    ]


def test_collect_golden_set_metrics_tolerates_redacted_token_counts(tmp_path: Path) -> None:
    benchmark = _load_benchmark_module()
    workspace = tmp_path / "workspace"
    manifest = tmp_path / "golden.json"
    manifest.write_text(
        json.dumps({"cases": [{"case_id": "redacted", "job_id": "job_redacted"}]}),
        encoding="utf-8",
    )
    _write_json(
        workspace / "jobs" / "job_redacted" / "07_gate_validation" / "gate_results.json",
        [{"name": "Gate", "status": "pass", "critical": True}],
    )
    _write_json(
        workspace / "jobs" / "job_redacted" / "logs" / "model_calls" / "a.json",
        {
            "task": "codegen",
            "result": {
                "latency_ms": 1_000,
                "usage": {
                    "prompt_tokens": "<redacted>",
                    "completion_tokens": "<redacted>",
                    "total_tokens": "<redacted>",
                },
            },
        },
    )

    summary = benchmark.collect_golden_set_metrics(workspace, manifest)

    assert summary["aggregate"]["model_calls"]["total_calls"] == 1
    assert summary["aggregate"]["model_calls"]["total_tokens"] == 0
