from __future__ import annotations

from agent_core.app import JobStatus, RadAgentEvent
from agent_core.tui.adapters import (
    event_to_row,
    render_header,
    render_markdown_row,
    render_row,
    render_startup_status,
    render_task_context,
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
