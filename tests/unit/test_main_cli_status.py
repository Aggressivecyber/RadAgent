from __future__ import annotations

import asyncio
import json
from pathlib import Path

from agent_core.main import check_status
from agent_core.workspace.paths import (
    STAGE_CONTEXT,
    STAGE_GATE_VALIDATION,
    STAGE_INPUT,
    STAGE_MODEL_IR,
    STAGE_REPORT,
    STAGE_TASK_PLAN,
)


def test_check_status_uses_current_workspace_stage_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
    job_dir = tmp_path / "jobs" / "status_job"
    files = {
        STAGE_INPUT: ("user_query.md", "query"),
        STAGE_CONTEXT: ("evidence_map.json", "{}"),
        STAGE_TASK_PLAN: ("task_spec.json", "{}"),
        STAGE_MODEL_IR: ("g4_model_ir.json", "{}"),
        STAGE_REPORT: ("final_report.md", "# Report"),
    }
    for stage, (filename, content) in files.items():
        stage_dir = job_dir / stage
        stage_dir.mkdir(parents=True)
        (stage_dir / filename).write_text(content, encoding="utf-8")

    gate_dir = job_dir / STAGE_GATE_VALIDATION
    gate_dir.mkdir(parents=True)
    (gate_dir / "gate_results.json").write_text(
        json.dumps(
            [
                {"gate_id": 0, "status": "pass"},
                {"gate_id": 1, "status": "fail"},
            ]
        ),
        encoding="utf-8",
    )

    status = asyncio.run(check_status("status_job"))

    assert status["status"] == "found"
    assert all(item["exists"] for item in status["artifacts"].values())
    assert status["gates_summary"] == "1/2 passed"
