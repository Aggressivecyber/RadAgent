from __future__ import annotations

from datetime import datetime

from agent_core.app import JobStatus, RadAgentEvent
from agent_core.tui.models import HeaderState, TimelineRow

_EVENT_TITLES = {
    "intent_classified": "Intent",
    "job_started": "Job started",
    "job_resumed": "Job resumed",
    "job_finished": "Job complete",
    "phase_started": "Phase started",
    "phase_finished": "Phase complete",
    "phase_failed": "Phase failed",
    "human_confirmation_required": "Needs confirmation",
    "human_confirmation_submitted": "Confirmation submitted",
    "chat_started": "User",
    "chat_finished": "Agent",
    "chat_failed": "Chat failed",
    "build_started": "Build started",
    "build_finished": "Build finished",
    "simulation_started": "Simulation started",
    "simulation_finished": "Simulation finished",
    "project_created": "Project created",
    "project_switched": "Project switched",
}

_PHASE_LABELS = {
    "prepare_workspace": "Prepare workspace",
    "context": "Context",
    "task_planning": "Task planning",
    "g4_modeling": "G4 modeling",
    "human_confirmation": "Human confirmation",
    "g4_codegen": "G4 codegen",
    "patch": "Patch",
    "gate": "Gate checks",
    "artifact": "Artifacts",
    "report": "Report",
}


def event_to_row(event: RadAgentEvent) -> TimelineRow:
    """Convert a service event into a stable timeline row."""
    event_type = event.event_type
    kind = _kind_for_event(event_type)
    title = _title_for_event(event)
    summary = _summary_for_event(event)
    return TimelineRow(
        id=_row_id(event),
        kind=kind,
        status=event.status,
        title=title,
        summary=summary,
        phase=event.phase,
        job_id=event.job_id,
        payload=dict(event.payload),
    )


def status_to_header(status: JobStatus, *, project: str = "default") -> HeaderState:
    """Convert service status into the fixed header model."""
    phase = "" if status.status == "idle" else status.current_phase
    return HeaderState(
        project=project or "default",
        job_id=status.job_id,
        status=status.status,
        phase=phase,
        execution_mode=status.execution_mode,
        run_mode=status.run_mode,
        needs_confirmation=status.needs_confirmation,
    )


def row_status_marker(status: str) -> str:
    """Return an ASCII status marker for terminals without color."""
    return {
        "running": "run",
        "success": "ok",
        "warning": "warn",
        "error": "err",
        "info": "info",
    }.get(status, "--")


def render_row(row: TimelineRow) -> str:
    """Render a compact one-line timeline row for Textual Static widgets."""
    role = row_role_label(row)
    marker = row_status_marker(row.status)
    if row.kind == "user_message":
        return f"{role:<7} {row.summary}"
    if row.kind == "assistant_message":
        return f"{role:<7} {row.title}"
    summary = f"  {row.summary}" if row.summary else ""
    return f"{role:<7} {marker:<4} {row.title}{summary}"


def render_markdown_row(row: TimelineRow) -> str:
    """Render an assistant row with Markdown formatting preserved."""
    role = row_role_label(row)
    return f"**{role}**\n\n{row.summary}"


def row_role_label(row: TimelineRow) -> str:
    """Return a short role label for timeline display."""
    return {
        "assistant_message": "AGENT",
        "confirmation": "REVIEW",
        "error": "ERROR",
        "phase": "RUN",
        "system": "SYSTEM",
        "tool": "TOOL",
        "user_message": "USER",
    }.get(row.kind, "EVENT")


def row_css_class(row: TimelineRow) -> str:
    """Return Textual CSS classes for a timeline row."""
    role_class = {
        "assistant_message": "role-agent",
        "confirmation": "role-review",
        "error": "role-error",
        "phase": "role-run",
        "system": "role-system",
        "tool": "role-tool",
        "user_message": "role-user",
    }.get(row.kind, "role-event")
    return f"row {role_class} status-{row.status}"


def render_header(header: HeaderState) -> str:
    """Render compact header text."""
    job = header.job_id or "no-job"
    phase = header.phase or "idle"
    confirm = "  review" if header.needs_confirmation else ""
    return (
        f"RadAgent  project/{header.project}  {job}  "
        f"status:{header.status}  phase:{phase}  mode:{header.run_mode}{confirm}"
    )


def _kind_for_event(event_type: str) -> str:
    if event_type == "chat_started":
        return "user_message"
    if event_type == "chat_finished":
        return "assistant_message"
    if event_type.startswith("phase_") or event_type.startswith("job_"):
        return "phase"
    if event_type.startswith("human_confirmation"):
        return "confirmation"
    if event_type.startswith(("build_", "simulation_")):
        return "tool"
    if event_type.endswith("_failed"):
        return "error"
    return "system"


def _title_for_event(event: RadAgentEvent) -> str:
    if event.phase and event.event_type.startswith("phase_"):
        phase = _PHASE_LABELS.get(event.phase, event.phase.replace("_", " ").title())
        suffix = {
            "phase_started": "running",
            "phase_finished": "passed",
            "phase_failed": "failed",
        }.get(event.event_type, "")
        return f"{phase} {suffix}".strip()
    return _EVENT_TITLES.get(event.event_type, event.event_type.replace("_", " ").title())


def _summary_for_event(event: RadAgentEvent) -> str:
    if event.event_type in {"chat_started", "chat_finished"}:
        message = event.payload.get("message", "")
        if isinstance(message, str) and message:
            return message
        return event.summary
    if event.phase:
        return event.summary or event.phase
    if event.summary:
        return event.summary
    if event.payload:
        return ", ".join(sorted(event.payload.keys())[:4])
    return ""


def _row_id(event: RadAgentEvent) -> str:
    created_at = event.created_at
    if isinstance(created_at, datetime):
        timestamp = created_at.isoformat()
    else:
        timestamp = str(created_at)
    return ":".join(
        part
        for part in (
            event.run_id,
            event.job_id,
            event.event_type,
            event.phase,
            timestamp,
        )
        if part
    )
