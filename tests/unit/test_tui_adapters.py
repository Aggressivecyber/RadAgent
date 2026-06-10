from __future__ import annotations

from agent_core.app import JobStatus, RadAgentEvent
from agent_core.tui.adapters import (
    event_to_row,
    render_header,
    render_markdown_row,
    render_row,
    status_to_header,
)


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
    assert render_markdown_row(row) == f"**AGENT**\n\n{full_message}"


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
