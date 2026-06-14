from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


def _load_inspector() -> Any:
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "inspect_job_logs.py"
    spec = importlib.util.spec_from_file_location("inspect_job_logs", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_resolve_job_dir_accepts_workspace_root_with_single_job(tmp_path: Path) -> None:
    inspector = _load_inspector()
    workspace = tmp_path / "workspace"
    job_dir = workspace / "jobs" / "job_real"
    (job_dir / "logs").mkdir(parents=True)
    (job_dir / "logs" / "events.jsonl").write_text("", encoding="utf-8")

    assert inspector._resolve_job_dir(str(workspace)) == job_dir


def test_build_summary_reports_model_call_distribution_and_failure_taxonomy(
    tmp_path: Path,
) -> None:
    inspector = _load_inspector()
    job_dir = tmp_path / "jobs" / "real"
    logs_dir = job_dir / "logs"
    logs_dir.mkdir(parents=True)
    failure_text = (
        "src/OutputManager.cc:264:7: error: 'fGeometryComponents' was not declared in this scope\n"
        "Missing output contract files: geometry_view.json, particle_tracks.json, energy_deposits.json\n"
    )
    (logs_dir / "events.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_type": "global_integration_runtime_gate_result",
                        "status": "failed",
                        "module_name": "global_integration_agent",
                        "summary": "Runtime gate attempt 0 fail",
                        "errors": [failure_text],
                    }
                ),
                json.dumps(
                    {
                        "event_type": "model_call",
                        "status": "passed",
                        "module_name": "runtime_app",
                        "duration_ms": 110_000,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    _write_json(
        logs_dir / "model_calls" / "1_runtime_app_codegen.json",
        {
            "status": "passed",
            "task": "codegen",
            "tier": "pro",
            "metadata": {"module_name": "runtime_app"},
            "started_at_unix": 1.0,
            "updated_at_unix": 111.0,
            "request": {
                "system_prompt": "s" * 10,
                "user_prompt": "u" * 90,
                "messages": None,
            },
        },
    )
    _write_json(
        logs_dir / "model_calls" / "2_agentic_repair_codegen.json",
        {
            "status": "passed",
            "task": "codegen",
            "tier": "pro",
            "metadata": {"module_name": "agentic_repair"},
            "started_at_unix": 2.0,
            "updated_at_unix": 7.0,
            "request": {
                "system_prompt": "",
                "user_prompt": "",
                "messages": [{"role": "user", "content": "m" * 200}],
            },
        },
    )
    _write_json(
        job_dir / "05_codegen" / "integration" / "agentic_repair_lessons.json",
        {
            "schema_version": "agentic_repair_lessons_v1",
            "lessons": [
                {
                    "id": "geometry_view_phantom_member",
                    "prompt_instruction": "Check OutputManager.hh before using fGeometryComponents.",
                    "count": 2,
                }
            ],
        },
    )

    summary = inspector.build_summary(job_dir)

    assert summary["model_call_summary"]["total"] == 2
    assert summary["model_call_summary"]["counts_by_module"] == {
        "agentic_repair": 1,
        "runtime_app": 1,
    }
    assert summary["model_call_summary"]["largest_prompt_chars"][0]["module_name"] == (
        "agentic_repair"
    )
    assert summary["model_call_summary"]["max_prompt_chars_by_module"] == {
        "agentic_repair": 200,
        "runtime_app": 100,
    }
    assert summary["model_call_summary"]["slowest_calls"][0]["module_name"] == (
        "runtime_app"
    )
    taxonomy = summary["failure_taxonomy"]
    assert taxonomy["counts"]["geometry_view_phantom_member"] == 1
    assert taxonomy["counts"]["missing_output_contract"] == 1
    assert taxonomy["counts"]["compile_error"] == 1
    assert summary["agentic_repair_lessons"]["lessons"][0]["id"] == (
        "geometry_view_phantom_member"
    )


def test_failure_taxonomy_labels_geant4_missing_type_and_signature_mismatch() -> None:
    inspector = _load_inspector()
    labels = inspector._failure_labels(
        "include/PlacementManager.hh:48:31: error: 'G4Material' has not been declared\n"
        "src/PlacementManager.cc:20:20: error: no declaration matches "
        "'G4VPhysicalVolume* PlacementManager::PlaceBox(...)'"
    )

    assert "compile_error" in labels
    assert "geant4_missing_type_include" in labels
    assert "signature_mismatch" in labels
