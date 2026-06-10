"""Tests for SQLite-backed RadAgent metadata storage."""

from __future__ import annotations

from pathlib import Path

from agent_core.storage import RadAgentStore
from agent_core.workspace.paths import STAGE_REPORT


def test_store_initializes_default_project(tmp_path: Path) -> None:
    store = RadAgentStore(workspace_root=tmp_path)

    project = store.current_project()

    assert project["slug"] == "default"
    assert project["name"] == "Default Project"
    assert (tmp_path / "radagent.db").exists()


def test_project_switching(tmp_path: Path) -> None:
    store = RadAgentStore(workspace_root=tmp_path)
    project = store.create_project("Detector Runs", slug="detectors")

    selected = store.set_current_project("detectors")

    assert selected is not None
    assert selected["id"] == project["id"]
    assert store.current_project()["slug"] == "detectors"


def test_job_upsert_and_list_are_project_scoped(tmp_path: Path) -> None:
    store = RadAgentStore(workspace_root=tmp_path)
    default = store.current_project()
    other = store.create_project("Other", slug="other")

    store.upsert_job(
        job_id="job-default",
        user_query="default query",
        project_id=default["id"],
        status="running",
        current_phase="context",
    )
    store.upsert_job(
        job_id="job-other",
        user_query="other query",
        project_id=other["id"],
        status="completed",
        current_phase="report",
    )

    default_jobs = store.list_jobs(project_id=default["id"])
    all_jobs = store.list_jobs(include_all_projects=True)

    assert [j["job_id"] for j in default_jobs] == ["job-default"]
    assert {j["job_id"] for j in all_jobs} == {"job-default", "job-other"}
    assert store.get_job("job-other")["status"] == "completed"


def test_state_snapshot_round_trip(tmp_path: Path) -> None:
    store = RadAgentStore(workspace_root=tmp_path)
    store.upsert_job(job_id="resume-me", user_query="simulate")
    state = {
        "job_id": "resume-me",
        "user_query": "simulate",
        "execution_mode": "strict",
        "g4_model_ir_path": "/tmp/model.json",
    }

    store.save_state_snapshot(
        job_id="resume-me",
        state=state,
        completed_phases=["prepare_workspace", "context"],
        phase="task_planning",
        current_phase_idx=2,
        status="paused",
    )

    snapshot = store.latest_state_snapshot("resume-me")

    assert snapshot is not None
    assert snapshot["state"] == state
    assert snapshot["completed_phases"] == ["prepare_workspace", "context"]
    assert snapshot["current_phase_idx"] == 2
    assert store.get_job("resume-me")["status"] == "paused"


def test_record_artifact_indexes_file_metadata(tmp_path: Path) -> None:
    store = RadAgentStore(workspace_root=tmp_path)
    store.upsert_job(job_id="artifact-job", user_query="simulate")
    artifact = tmp_path / "jobs" / "artifact-job" / STAGE_REPORT / "final_report.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("report", encoding="utf-8")

    store.record_artifact(
        job_id="artifact-job",
        path=str(artifact),
        stage=STAGE_REPORT,
        kind="final_report",
        mime_type="text/markdown",
    )

    row = store.conn.execute(
        "SELECT * FROM artifacts WHERE job_id = ?",
        ("artifact-job",),
    ).fetchone()
    assert row is not None
    assert row["path"] == str(artifact)
    assert row["size_bytes"] == len("report")
    assert len(row["sha256"]) == 64
