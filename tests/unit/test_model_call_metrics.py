from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_metrics_module() -> Any:
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "model_call_metrics.py"
    spec = importlib.util.spec_from_file_location("model_call_metrics", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_collect_metrics_aggregates_model_latency_and_agentic_stops(tmp_path: Path) -> None:
    metrics = _load_metrics_module()
    workspace = tmp_path / "workspace"
    job_dir = workspace / "jobs" / "job_a"

    _write_json(
        job_dir / "logs" / "model_calls" / "1_codegen.json",
        {
            "status": "passed",
            "task": "codegen",
            "tier": "pro",
            "model_name": "mimo-v2.5-pro",
            "metadata": {"module_name": "agentic_repair"},
            "result": {"latency_ms": 10_000, "error": None},
        },
    )
    _write_json(
        job_dir / "logs" / "model_calls" / "2_codegen.json",
        {
            "status": "failed",
            "task": "codegen",
            "tier": "pro",
            "model_name": "mimo-v2.5-pro",
            "metadata": {"module_name": "runtime_app"},
            "started_at_unix": 1.0,
            "updated_at_unix": 31.0,
            "result": {"error": "timeout"},
        },
    )
    _write_json(
        job_dir / "05_codegen" / "global_integration_agent_report.json",
        {
            "status": "failed",
            "agentic": {
                "stop_reason": "max_turns",
                "n_turns": 12,
                "tool_calls": 20,
                "tool_audit": [
                    {"turn": 0, "name": "build_project", "ok": False},
                    {"turn": 3, "name": "run_smoke", "ok": False},
                    {"turn": 7, "name": "run_smoke", "ok": True},
                ],
            },
        },
    )

    summary = metrics.collect_metrics(workspace)

    assert summary["model_calls"]["total"] == 2
    assert summary["model_calls"]["by_task"]["codegen"]["count"] == 2
    assert summary["model_calls"]["by_task"]["codegen"]["p50_s"] == 20.0
    assert summary["model_calls"]["by_task"]["codegen"]["p95_s"] == 30.0
    assert summary["model_calls"]["by_module"]["runtime_app"]["errors"] == 1
    assert summary["agentic"]["stop_reasons"] == {"max_turns": 1}
    assert summary["agentic"]["turns"]["max"] == 12
    assert summary["agentic"]["turn_to_first_smoke"]["values"] == [3]
    assert summary["agentic"]["turn_to_first_passing_smoke"]["values"] == [7]
