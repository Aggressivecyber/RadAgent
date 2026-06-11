from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_core.app import JobStatus, RadAgentEvent
from agent_core.pipeline import PIPELINE_PHASES
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
    "copilot_started": "User",
    "copilot_finished": "Copliot",
    "copilot_failed": "Copliot failed",
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
    if row.kind == "brand":
        return row.summary
    role = row_role_label(row)
    marker = row_status_marker(row.status)
    if row.kind == "user_message":
        return f"{role:<7} {row.summary}"
    if row.kind == "assistant_message":
        return f"{role:<7} {row.title}"
    if row.kind == "thinking":
        return f"{role:<7} {marker:<4} {row.summary}"
    summary = f"  {row.summary}" if row.summary else ""
    return f"{role:<7} {marker:<4} {row.title}{summary}"


def render_markdown_row(row: TimelineRow) -> str:
    """Render an assistant row with Markdown formatting preserved."""
    role = row_role_label(row)
    return f"**{role}**\n\n{row.summary}"


def row_role_label(row: TimelineRow) -> str:
    """Return a short role label for timeline display."""
    return {
        "assistant_message": "Copliot",
        "confirmation": "REVIEW",
        "error": "ERROR",
        "phase": "RUN",
        "system": "SYSTEM",
        "thinking": "Copliot",
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
        "thinking": "role-agent",
        "tool": "role-tool",
        "user_message": "role-user",
    }.get(row.kind, "role-event")
    return f"row {role_class} status-{row.status}"


def render_header(header: HeaderState) -> str:
    """Render compact header text."""
    job = f"job:{header.job_id}" if header.job_id else "job:none"
    phase = header.phase or "idle"
    confirm = "  review" if header.needs_confirmation else ""
    return (
        f"RadAgent  project/{header.project}  {job}  "
        f"status:{header.status}  phase:{phase}  mode:{header.run_mode}{confirm}"
    )


def render_startup_status(status: Any) -> str:
    """Render the startup status frame as a workstation-style overview."""
    tools = _mapping(status, "tools", {})
    models = _mapping(status, "models", {})
    project = _value(status, "project_slug", "default")
    workspace = _value(status, "workspace_root", "")
    lines = [
        "Workspace",
        f"{'Project':<13}{project}",
        f"{'Directory':<13}{workspace or 'unset'}",
        f"{'Runtime':<13}idle",
        "",
        "Environment",
        f"{'Tool':<12}{'Status':<12}Path / Note",
        _tool_status_line(tools.get("geant4"), "Geant4"),
        _tool_status_line(tools.get("tcad"), "TCAD"),
        _tool_status_line(tools.get("ngspice"), "ngspice"),
        "",
        "Models",
        f"{'Profile':<12}{'Model':<15}{'Access':<11}Capability",
    ]
    for tier_name in ("lite", "pro", "max"):
        model = models.get(tier_name)
        if model is None:
            lines.append(f"{tier_name:<12}{'missing':<15}{'no-key':<11}unknown")
            continue
        key_status = "key" if _value(model, "api_key_configured", False) else "no-key"
        capability = "think" if _value(model, "thinking_default", False) else "normal"
        lines.append(
            f"{tier_name:<12}{_value(model, 'model_name', 'unset'):<15}"
            f"{key_status:<11}{capability}"
        )
    lines.extend(
        [
            "",
            "System Log",
            "[OK]      Workspace initialized",
            "[OK]      Environment inspected",
            "[OK]      Model profiles loaded",
        ]
    )
    return "\n".join(lines)


def render_task_context(status: JobStatus, *, language: Any = "en") -> str:
    """Render the right-side task summary and adjacent workflow steps."""
    phase = (
        _PHASE_LABELS.get(status.current_phase, status.current_phase.replace("_", " ").title())
        if status.current_phase
        else "waiting"
    )
    lines = [
        "Task",
        f"{'Job':<13}{status.job_id or 'no-job'}",
        f"{'State':<13}{status.status or 'idle'}",
        f"{'Phase':<13}{phase}",
    ]
    summary = _summary_for_language(
        status.state.get("task_summary_short"),
        language=language,
    )
    if summary:
        lines.extend(["", "Next Action", summary])
    lines.extend(["", "Context", *_context_usage_lines(status.state.get("copilot_context_usage"))])
    lines.extend(["", "Workflow", *_workflow_step_lines(status)])
    return "\n".join(lines)


def _kind_for_event(event_type: str) -> str:
    if event_type == "copilot_started":
        return "user_message"
    if event_type == "copilot_finished":
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
    if event.event_type in {"copilot_started", "copilot_finished"}:
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


def _tool_status_line(tool: Any, fallback_label: str) -> str:
    if tool is None:
        return f"{fallback_label:<12}{'MISSING':<12}-"
    label = _value(tool, "label", fallback_label)
    configured = bool(_value(tool, "configured", False))
    available = bool(_value(tool, "available", False))
    detail = str(_value(tool, "detail", "") or "")
    lower_detail = detail.lower()
    if available and "missing" not in lower_detail:
        state = "READY"
    elif configured or available:
        state = "PARTIAL"
    else:
        state = "MISSING"
    note = str(_value(tool, "path", "") or detail or "-")
    return f"{label:<12}{state:<12}{_shorten_middle(note, 42)}".rstrip()


def _summary_for_language(value: Any, *, language: Any) -> str:
    if not isinstance(value, dict):
        return ""
    selected = getattr(language, "value", str(language))
    key = "zh" if selected == "zh" else "en"
    summary = str(value.get(key) or value.get("en") or value.get("zh") or "").strip()
    return summary[:50]


def _workflow_step_lines(status: JobStatus) -> list[str]:
    index = _current_phase_index(status)
    previous_index = index - 1 if index > 0 else None
    next_index = index + 1 if index + 1 < len(PIPELINE_PHASES) else None
    return [
        _workflow_line("✓", "Previous", previous_index),
        _workflow_line("●", "Current", index),
        _workflow_line("○", "Next", next_index),
    ]


def _current_phase_index(status: JobStatus) -> int:
    if status.current_phase in PIPELINE_PHASES:
        return PIPELINE_PHASES.index(status.current_phase)
    return max(0, min(int(status.current_phase_idx), len(PIPELINE_PHASES) - 1))


def _workflow_line(symbol: str, role: str, index: int | None) -> str:
    label = (
        _PHASE_LABELS.get(PIPELINE_PHASES[index], PIPELINE_PHASES[index])
        if index is not None
        else "-"
    )
    return f"{symbol} {role:<12} {label}".rstrip()


def _context_usage_lines(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return [
            f"{'Usage':<13}0%",
            f"{'Mode':<13}normal",
            f"{'Window':<13}128k",
        ]
    ratio = _float_value(value.get("history_usage_ratio"))
    percent = max(0, min(999, round(ratio * 100)))
    state = str(value.get("state") or ("compacted" if value.get("compacted") else "normal"))
    cycle = int(value.get("cycle") or 0)
    window = _format_window_k(value.get("context_window_tokens"))
    if state == "compacting":
        return [
            f"{'Usage':<13}compacting cycle {cycle}".strip(),
            f"{'Mode':<13}compacting",
            f"{'Window':<13}{window or 'unknown'}",
        ]
    bar = _progress_bar(ratio)
    suffix = f"cycle {cycle}" if cycle else "normal"
    if state == "compacted":
        suffix = f"cycle {cycle} compacted".strip()
    return [
        f"{'Usage':<13}{bar} {percent}% {suffix}".strip(),
        f"{'Mode':<13}{state}",
        f"{'Window':<13}{window or 'unknown'}",
    ]


def _progress_bar(ratio: float, *, width: int = 10) -> str:
    filled = max(0, min(width, round(ratio * width)))
    return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_window_k(value: Any) -> str:
    try:
        tokens = int(value)
    except (TypeError, ValueError):
        return ""
    if tokens <= 0:
        return ""
    if tokens % 1_000_000 == 0:
        return f"{tokens // 1_000_000}m"
    return f"{tokens // 1000}k"


def _mapping(value: Any, key: str, default: Any) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _value(value: Any, key: str, default: Any = "") -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _shorten_middle(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    keep = max_len - 3
    front = keep // 2
    back = keep - front
    return f"{value[:front]}...{value[-back:]}"


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
