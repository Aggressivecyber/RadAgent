from __future__ import annotations

import json
from pathlib import Path

from agent_core.graph.main_graph import _load_runtime_failure_context
from agent_core.workspace.paths import STAGE_GATE_VALIDATION


def test_codegen_retry_loads_gate_failure_artifacts(tmp_path: Path) -> None:
    job_dir = tmp_path / "jobs" / "retry_job"
    gate_dir = job_dir / STAGE_GATE_VALIDATION
    output_dir = gate_dir / "g4_output_package"
    output_dir.mkdir(parents=True)

    smoke_path = output_dir / "smoke_simulation_result.json"
    smoke_path.write_text(
        json.dumps(
            {
                "success": False,
                "errors": "BeamOn ignored because /run/initialize is missing",
            }
        ),
        encoding="utf-8",
    )
    build_path = output_dir / "build_result.json"
    build_path.write_text(
        json.dumps(
            {
                "success": False,
                "errors": "MaterialRegistry.cc: invalid operands to binary expression",
            }
        ),
        encoding="utf-8",
    )
    logs_dir = job_dir / "logs"
    logs_dir.mkdir()
    (logs_dir / "failure_bundle.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "phase": "gate_validation",
                "errors": ["Build failed"],
                "warnings": [],
                "details": {"failed_gates": [{"gate_id": 6, "message": "Build failed"}]},
            }
        ),
        encoding="utf-8",
    )
    gate_results_path = gate_dir / "gate_results.json"
    gate_results_path.write_text(
        json.dumps(
            [
                {
                    "gate_id": 6,
                    "name": "Build/Parse",
                    "status": "fail",
                    "message": "Build failed",
                    "failed_items": ["Build failed"],
                    "warnings": [],
                    "file_paths": [str(build_path)],
                },
                {
                    "gate_id": 9,
                    "name": "Smoke Simulation",
                    "status": "fail",
                    "message": "Smoke failed",
                    "failed_items": ["Smoke failed"],
                    "warnings": [],
                    "file_paths": [str(smoke_path)],
                }
            ]
        ),
        encoding="utf-8",
    )

    context = _load_runtime_failure_context(
        {
            "job_id": "retry_job",
            "job_workspace": str(job_dir),
            "gate_results_path": str(gate_results_path),
            "retry_count": 1,
        }
    )

    assert context["source"] == "gate_validation_retry"
    assert context["failed_gates"][0]["gate_id"] == 6
    assert "Build failed" in context["build_errors"]
    assert context["failure_bundle"]["status"] == "failed"
    assert context["artifacts"]
    artifact_text = "\n".join(item["tail"] for item in context["artifacts"])
    assert "BeamOn ignored" in artifact_text
    assert "invalid operands to binary expression" in artifact_text
