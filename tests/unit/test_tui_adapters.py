from __future__ import annotations

from agent_core.app import JobStatus, RadAgentEvent
from agent_core.tui.adapters import (
    event_to_row,
    render_artifacts_table,
    render_command_palette,
    render_error_state,
    render_header,
    render_job_detail,
    render_jobs_table,
    render_markdown_row,
    render_row,
    render_startup_status,
    render_task_context,
    render_tool_inspect,
    status_to_header,
)
from agent_core.tui.i18n import RADAGENT_BRAND_MARK
from agent_core.tui.models import TimelineRow


def test_event_to_row_maps_phase_event() -> None:
    event = RadAgentEvent(
        event_type="phase_finished",
        status="success",
        phase="g4_modeling",
        summary="Finished modeling",
        job_id="job_1",
        run_id="run_1",
    )

    row = event_to_row(event)

    assert row.kind == "phase"
    assert row.status == "success"
    assert row.title == "G4 modeling passed"
    assert row.summary == "Finished modeling"
    assert "phase_finished" in row.id
    assert render_row(row).startswith("RUN")
    assert "ok" in render_row(row)


def test_event_to_row_uses_full_chat_payload() -> None:
    full_message = "**bold** " * 40
    event = RadAgentEvent(
        event_type="copilot_finished",
        status="success",
        summary=full_message[:120],
        payload={"message": full_message},
    )

    row = event_to_row(event)

    assert row.kind == "assistant_message"
    assert row.summary == full_message
    assert render_markdown_row(row) == f"**Copliot**\n\n{full_message}"


def test_brand_row_renders_without_status_prefix() -> None:
    row = TimelineRow(
        id="brand",
        kind="brand",
        status="info",
        title="RadAgent",
        summary=RADAGENT_BRAND_MARK,
    )

    rendered = render_row(row)

    assert not rendered.startswith("EVENT")
    assert "[red]" not in rendered
    assert rendered == RADAGENT_BRAND_MARK


def test_status_to_header_renders_confirmation_state() -> None:
    status = JobStatus(
        job_id="job_1",
        status="paused",
        current_phase="human_confirmation",
        run_mode="strict",
        needs_confirmation=True,
    )

    header = status_to_header(status, project="default")

    assert header.needs_confirmation is True
    assert "review" in render_header(header)
    assert "job_1" in render_header(header)


def test_task_context_renders_copliot_context_usage_bar() -> None:
    status = JobStatus(
        job_id="job_1",
        status="idle",
        state={
                "copilot_context_usage": {
                    "history_usage_ratio": 0.76,
                    "threshold": 0.75,
                    "state": "normal",
                    "cycle": 2,
                    "context_window_tokens": 200_000,
                }
            },
    )

    rendered = render_task_context(status)

    assert "Context" in rendered
    assert "Usage        [########--] 76%" in rendered
    assert "Mode         normal" in rendered
    assert "Window       200k" in rendered
    assert "Copliot context" not in rendered
    assert "[########--]" in rendered
    assert "76%" in rendered
    assert "cycle 2" in rendered
    assert "200k" in rendered


def test_task_context_renders_context_compacting_state() -> None:
    status = JobStatus(
        job_id="job_1",
        status="idle",
        state={
            "copilot_context_usage": {
                "history_usage_ratio": 0.92,
                "threshold": 0.75,
                "state": "compacting",
                "cycle": 3,
                "context_window_tokens": 500_000,
            }
        },
    )

    rendered = render_task_context(status)

    assert "Context" in rendered
    assert "compacting" in rendered
    assert "cycle 3" in rendered
    assert "500k" in rendered


def test_task_context_renders_runtime_monitor_simulation_summary_and_ascii_chart() -> None:
    status = JobStatus(
        job_id="job_electron",
        status="running",
        current_phase="artifact",
        current_phase_idx=8,
        completed_phases=[
            "prepare_workspace",
            "context",
            "task_planning",
            "g4_modeling",
            "human_confirmation",
            "g4_codegen",
            "patch",
            "gate",
        ],
        state={
            "runtime_monitor": {
                "cpu_percent": 18,
                "memory_gb": 2.1,
                "disk_free_gb": 42,
                "events_done": 32000,
                "events_total": 100000,
                "speed": "1200 evt/s",
            },
            "simulation_summary": {
                "Particle": "electron",
                "Energy": "7 MeV",
                "Target": "aluminum",
                "Thickness": "10 cm",
                "Detector": "silicon",
                "Events": "100000",
            },
            "ascii_chart": {
                "title": "Energy Deposit",
                "bins": [
                    ("0 cm", 1.0),
                    ("2 cm", 0.8),
                    ("4 cm", 0.5),
                    ("6 cm", 0.2),
                ],
            },
        },
    )

    rendered = render_task_context(status)

    assert "Runtime" in rendered
    assert "CPU          18%" in rendered
    assert "Events       32000 / 100000" in rendered
    assert "Simulation" in rendered
    assert "Particle     electron" in rendered
    assert "Energy       7 MeV" in rendered
    assert "Energy Deposit" in rendered
    assert "0 cm" in rendered
    assert "██████████" in rendered


def test_workflow_renders_warning_failure_and_retry_markers() -> None:
    warning = render_task_context(
        JobStatus(
            job_id="job_review",
            status="paused",
            current_phase="human_confirmation",
            current_phase_idx=4,
            completed_phases=["prepare_workspace", "context", "task_planning"],
            needs_confirmation=True,
        )
    )
    failed = render_task_context(
        JobStatus(
            job_id="job_failed",
            status="failed",
            current_phase="gate",
            current_phase_idx=7,
            completed_phases=[
                "prepare_workspace",
                "context",
                "task_planning",
                "g4_modeling",
                "human_confirmation",
                "g4_codegen",
                "patch",
            ],
        )
    )
    retrying = render_task_context(
        JobStatus(
            job_id="job_retry",
            status="running",
            current_phase="g4_codegen",
            current_phase_idx=5,
            completed_phases=[
                "prepare_workspace",
                "context",
                "task_planning",
                "g4_modeling",
                "human_confirmation",
            ],
            state={"retry_count": 1},
        )
    )

    assert "! Plan simulation" in warning
    assert "× Run checks / tools" in failed
    assert "↻ Generate macro / script" in retrying


def test_startup_status_renders_workstation_sections_and_semantic_tool_states() -> None:
    status = {
        "project_slug": "default",
        "workspace_root": "/tmp/simulation_workspace",
        "tools": {
            "geant4": {
                "label": "Geant4",
                "configured": True,
                "available": True,
                "path": "/usr/local/bin/geant4-config",
                "detail": "config=/usr/local/bin/geant4-config",
            },
            "tcad": {
                "label": "TCAD",
                "configured": True,
                "available": False,
                "path": "",
                "detail": "dir=unset; sde=ok; svisual=ok; swb=missing",
            },
            "ngspice": {
                "label": "ngspice",
                "configured": False,
                "available": False,
                "path": "",
                "detail": "set NGSPICE_BIN",
            },
        },
        "models": {
            "lite": {
                "model_name": "mimo-v2.5",
                "api_key_configured": True,
                "thinking_default": False,
            },
            "pro": {
                "model_name": "mimo-v2.5-pro",
                "api_key_configured": True,
                "thinking_default": True,
            },
            "max": {
                "model_name": "mimo-v2.5-pro",
                "api_key_configured": False,
                "thinking_default": True,
            },
        },
    }

    rendered = render_startup_status(status)

    assert "Workspace" in rendered
    assert "Project      default" in rendered
    assert "Directory    /tmp/simulation_workspace" in rendered
    assert "Environment" in rendered
    assert "Tool        Status      Path / Note" in rendered
    assert "Geant4      READY" in rendered
    assert "TCAD        PARTIAL" in rendered
    assert "ngspice     MISSING" in rendered
    assert "Models" in rendered
    assert "Profile     Model" in rendered
    assert "lite        mimo-v2.5" in rendered
    assert "pro         mimo-v2.5-pro" in rendered
    assert "System Log" in rendered
    assert "[OK]      Workspace initialized" in rendered


def test_tool_inspect_renders_versions_license_and_fix_suggestions() -> None:
    status = {
        "tools": {
            "geant4": {
                "label": "Geant4",
                "configured": True,
                "available": True,
                "path": "/opt/geant4/bin/geant4-config",
                "detail": "version=11.2.1; data=found",
            },
            "tcad": {
                "label": "TCAD",
                "configured": True,
                "available": False,
                "path": "",
                "detail": "sde=ok; sdevice=ok; swb=missing; license=unknown",
            },
            "ngspice": {
                "label": "ngspice",
                "configured": True,
                "available": True,
                "path": "/usr/local/bin/ngspice",
                "detail": "version=41",
            },
        }
    }

    rendered = render_tool_inspect(status)

    assert "Tool Inspect" in rendered
    assert "Geant4" in rendered
    assert "Status       READY" in rendered
    assert "Version      11.2.1" in rendered
    assert "TCAD" in rendered
    assert "Status       PARTIAL" in rendered
    assert "SWB          MISSING" in rendered
    assert "License      UNKNOWN" in rendered
    assert "Fix Suggestion" in rendered
    assert "Add swb to PATH" in rendered


def test_artifacts_and_jobs_tables_are_productized() -> None:
    artifacts = [
        {
            "kind": "macro",
            "path": "./runs/job-001/run.mac",
            "size_bytes": 2100,
            "stage": "g4",
        },
        {
            "kind": "plot",
            "path": "./runs/job-001/energy_deposit.png",
            "size_bytes": 320_000,
            "stage": "report",
        },
    ]
    jobs = [
        {
            "job_id": "job-001",
            "user_query": "electron_aluminum_test",
            "status": "completed",
            "updated_at": "12:40",
        },
        {
            "job_id": "job-002",
            "user_query": "proton_silicon_detector",
            "status": "failed",
            "updated_at": "13:10",
        },
    ]

    artifact_table = render_artifacts_table(artifacts)
    jobs_table = render_jobs_table(jobs)

    assert "Type      Name" in artifact_table
    assert "macro     run.mac" in artifact_table
    assert "plot      energy_deposit.png" in artifact_table
    assert "320.0 KB" in artifact_table
    assert "Status" in artifact_table
    assert "Jobs" in jobs_table
    assert "ID        Name" in jobs_table
    assert "job-001   electron_aluminum_test" in jobs_table
    assert "completed" in jobs_table


def test_artifacts_table_preserves_semantic_status_values() -> None:
    artifacts = [
        {
            "kind": "log",
            "path": "./runs/job-001/geant4.log",
            "size_bytes": 18_000,
            "status": "generating",
        },
        {
            "kind": "report",
            "path": "./runs/job-001/summary.md",
            "size_bytes": 8_000,
            "status": "outdated",
        },
        {
            "kind": "plot",
            "path": "./runs/job-001/energy.png",
            "size_bytes": 0,
            "status": "failed",
        },
    ]

    rendered = render_artifacts_table(artifacts)

    assert "log       geant4.log" in rendered
    assert "generating" in rendered
    assert "report    summary.md" in rendered
    assert "outdated" in rendered
    assert "plot      energy.png" in rendered
    assert "failed" in rendered


def test_job_detail_renders_resume_retry_and_output_location() -> None:
    rendered = render_job_detail(
        {
            "job_id": "job-001",
            "user_query": "electron_aluminum_test",
            "status": "failed",
            "created_at": "2026-06-11 12:40",
            "current_phase": "gate",
            "run_mode": "strict",
            "execution_mode": "strict",
            "job_workspace": "./simulation_workspace/jobs/job-001",
            "error_summary": "macro syntax error",
        }
    )

    assert "Job Detail" in rendered
    assert "Name         electron_aluminum_test" in rendered
    assert "Status       failed" in rendered
    assert "Created      2026-06-11 12:40" in rendered
    assert "Phase        gate" in rendered
    assert "Output       ./simulation_workspace/jobs/job-001" in rendered
    assert "Error        macro syntax error" in rendered
    assert "/resume job-001" in rendered
    assert "/retry job-001" in rendered


def test_error_state_and_command_palette_are_actionable() -> None:
    rendered = render_error_state(
        "Geant4 config not found",
        suggestions=["Check GEANT4_DIR", "Source geant4.sh", "Run /check geant4"],
    )

    assert "ERROR" in rendered
    assert "Geant4 config not found" in rendered
    assert "Suggestion:" in rendered
    assert "1. Check GEANT4_DIR" in rendered

    palette = render_command_palette("/ch")
    assert "Command Palette" in palette
    assert "/check" in palette
    assert "Inspect Geant4 / TCAD / ngspice" in palette
