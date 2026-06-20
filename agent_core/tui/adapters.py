from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from agent_core.app import JobStatus, RadAgentEvent
from agent_core.pipeline import PIPELINE_PHASES
from agent_core.tui.commands import command_suggestions
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
    "copilot_finished": "Copilot",
    "copilot_failed": "Copilot failed",
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
    "requirements_review": "Requirements review",
    "g4_modeling": "G4 modeling",
    "human_confirmation": "Requirements review",
    "g4_codegen": "G4 codegen",
    "patch": "Patch",
    "gate": "Gate checks",
    "artifact": "Artifacts",
    "report": "Report",
}
_STANDARD_WORKFLOW = (
    ("parse_request", "Parse request", ()),
    ("prepare_workspace", "Prepare workspace", ("prepare_workspace",)),
    ("load_context", "Load context", ("context",)),
    ("plan_simulation", "Plan simulation", ("task_planning", "requirements_review", "g4_modeling", "human_confirmation")),
    ("generate_macro", "Generate macro / script", ("g4_codegen", "patch")),
    ("run_tools", "Run checks / tools", ("gate", "artifact")),
    ("generate_report", "Generate report", ("report",)),
)
_STARTUP_TASK_PLAN = (
    "Use lite LLM for briefing and modeling extraction.",
    "Generate Geant4 modules with agentic read/write/edit tools.",
    "Repair only from build_project and run_smoke feedback.",
    "Accept completion only after build, smoke, gate, artifact, report.",
    "Record handoff notes in radagent-tui-e2e-testing.md.",
)


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
        frame = str(row.payload.get("activity_frame") or "").strip()
        activity = f"{frame} {row.summary}" if frame else row.summary
        return f"{role:<7} {marker:<4} {activity}"
    summary = f"  {row.summary}" if row.summary else ""
    return f"{role:<7} {marker:<4} {row.title}{summary}"


def render_markdown_row(row: TimelineRow) -> str:
    """Render an assistant row with Markdown formatting preserved."""
    role = row_role_label(row)
    return f"**{role}**\n\n{row.summary}"


def row_role_label(row: TimelineRow) -> str:
    """Return a short role label for timeline display."""
    return {
        "assistant_message": "Copilot",
        "confirmation": "REVIEW",
        "error": "ERROR",
        "phase": "RUN",
        "system": "SYSTEM",
        "thinking": "Copilot",
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
        "RadAgent",
        "",
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
            "Task Plan",
            *[f"{index}. {item}" for index, item in enumerate(_STARTUP_TASK_PLAN, start=1)],
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
    current_phase = _present_phase(status.current_phase)
    phase = (
        _PHASE_LABELS.get(current_phase, current_phase.replace("_", " ").title())
        if current_phase
        else "completed" if status.status == "completed" else "waiting"
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
    runtime_lines = _runtime_monitor_lines(status.state.get("runtime_monitor"))
    if runtime_lines:
        lines.extend(["", "Runtime", *runtime_lines])
    simulation_lines = _simulation_summary_lines(status.state.get("simulation_summary"))
    if simulation_lines:
        lines.extend(["", "Simulation", *simulation_lines])
    chart_lines = _ascii_chart_lines(status.state.get("ascii_chart"))
    if chart_lines:
        lines.extend(["", *chart_lines])
    lines.extend(["", "Workflow", *_workflow_step_lines(status)])
    return "\n".join(lines)


def render_tool_inspect(status: Any) -> str:
    """Render detailed runtime tool status for the Inspect panel."""
    tools = _mapping(status, "tools", {})
    lines = ["Tool Inspect"]
    suggestions: list[str] = []
    for key, fallback in (("geant4", "Geant4"), ("tcad", "TCAD"), ("ngspice", "ngspice")):
        tool = tools.get(key)
        label = str(_value(tool, "label", fallback) if tool is not None else fallback)
        detail = str(_value(tool, "detail", "") if tool is not None else "")
        fields = _detail_fields(detail)
        state = _tool_state(tool)
        lines.extend(["", label, f"{'Status':<13}{state}"])
        version = fields.get("version")
        if version:
            lines.append(f"{'Version':<13}{version}")
        path = str(_value(tool, "path", "") if tool is not None else "")
        if path:
            lines.append(f"{'Path':<13}{path}")
        if key == "geant4":
            data = fields.get("data")
            if data:
                lines.append(f"{'Data':<13}{data.upper()}")
        if key == "tcad":
            for field, title in (
                ("sde", "SDE"),
                ("sdevice", "SDEVICE"),
                ("svisual", "SVISUAL"),
                ("swb", "SWB"),
            ):
                if field in fields:
                    lines.append(f"{title:<13}{_status_label(fields[field])}")
            if "license" in fields:
                lines.append(f"{'License':<13}{fields['license'].upper()}")
            if fields.get("swb", "").lower() == "missing":
                suggestions.append("Add swb to PATH")
            if fields.get("license", "").lower() in {"unknown", "missing", "unset"}:
                suggestions.append("Check license server")
        if state == "MISSING":
            suggestions.append(f"Configure {label}")
    if suggestions:
        lines.extend(["", "Fix Suggestion"])
        for item in dict.fromkeys(suggestions):
            lines.append(f"- {item}")
    return "\n".join(lines)


def render_artifacts_table(artifacts: list[Any]) -> str:
    """Render artifact summaries as a compact product table."""
    lines = ["Artifacts", "", f"{'Type':<10}{'Name':<24}{'Size':<11}Status"]
    if not artifacts:
        lines.append("No artifacts for the active job.")
        return "\n".join(lines)
    for item in artifacts[:30]:
        kind = str(_value(item, "kind", "") or _value(item, "stage", "") or "file")
        path = str(_value(item, "path", ""))
        size = _format_bytes(_value(item, "size_bytes", 0))
        status = str(_value(item, "status", "") or "ready")
        lines.append(f"{kind:<10}{Path(path).name:<24}{size:<11}{status}")
    return "\n".join(lines)


def render_jobs_table(jobs: list[dict[str, Any]]) -> str:
    """Render saved jobs as a compact session-management table."""
    lines = ["Jobs", "", f"{'ID':<10}{'Name':<29}{'Status':<12}Time"]
    if not jobs:
        lines.append("No jobs found.")
        return "\n".join(lines)
    for job in jobs[:30]:
        job_id = str(job.get("job_id", ""))
        name = _clip_table_text(str(job.get("user_query") or job.get("name") or "-"), 28)
        status = str(job.get("status", "unknown"))
        time = str(job.get("updated_at") or job.get("created_at") or "")
        lines.append(f"{job_id:<10}{name:<29}{status:<12}{time}")
    return "\n".join(lines)


def render_job_detail(job: dict[str, Any] | None) -> str:
    """Render one job as a resumable session detail panel."""
    if not job:
        return render_error_state(
            "Job not found.",
            suggestions=["Run /jobs", "Check the job id", "Use /resume <job_id>"],
        )
    job_id = str(job.get("job_id", ""))
    lines = [
        "Job Detail",
        "",
        f"{'Name':<13}{job.get('user_query') or job.get('name') or '-'}",
        f"{'Status':<13}{job.get('status', 'unknown')}",
        f"{'Created':<13}{job.get('created_at', '')}",
        f"{'Phase':<13}{job.get('current_phase') or 'idle'}",
        f"{'Mode':<13}{job.get('run_mode') or job.get('execution_mode') or 'strict'}",
    ]
    if job.get("job_workspace"):
        lines.append(f"{'Output':<13}{job['job_workspace']}")
    if job.get("error_summary"):
        lines.append(f"{'Error':<13}{job['error_summary']}")
    lines.extend(["", "Commands", f"/resume {job_id}", f"/retry {job_id}", f"/open {job_id}"])
    return "\n".join(lines)


def render_confirmation_review(review: dict[str, Any]) -> str:
    """Render the active human-confirmation review with decision actions."""
    if not review.get("report_path"):
        return render_error_state(
            "No confirmation report for the active job.",
            suggestions=["Run /status", "Resume a job", "Wait for modeling to finish"],
        )
    preview = str(review.get("preview", ""))
    lines = [
        "Confirmation",
        "",
        f"{'Status':<13}{review.get('status', '') or 'unknown'}",
        f"{'Required':<13}{'yes' if review.get('required') else 'no'}",
        f"{'Unconfirmed':<13}{review.get('unconfirmed_assumptions_count', 0)}",
        f"{'Report':<13}{review.get('report_path', '')}",
        "",
        "Actions",
        "/confirm approve",
        "/reject <reason>",
        "/ask-more <question>",
    ]
    if preview:
        lines.extend(["", "Preview", *preview.splitlines()[:180]])
    return "\n".join(lines)


def render_error_state(title: str, *, suggestions: list[str] | None = None) -> str:
    """Render an actionable error state with next steps."""
    lines = ["ERROR", title]
    if suggestions:
        lines.extend(["", "Suggestion:"])
        for index, suggestion in enumerate(suggestions, start=1):
            lines.append(f"{index}. {suggestion}")
    return "\n".join(lines)


def render_command_palette(prefix: str) -> str:
    """Render slash-command suggestions for the composer."""
    suggestions = command_suggestions(prefix)
    lines = ["Command Palette", ""]
    lines.extend(suggestions or ["No matching commands."])
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
    current = _present_phase(status.current_phase)
    if current not in PIPELINE_PHASES:
        current = ""
    completed = {_present_phase(phase) for phase in status.completed_phases}
    lines: list[str] = []
    for virtual_key, label, phases in _STANDARD_WORKFLOW:
        phase_set = set(phases)
        if virtual_key == "parse_request":
            symbol = "✓" if status.job_id or status.user_query else "●"
        elif current in phase_set:
            if status.status in {"failed", "error"}:
                symbol = "×"
            elif status.needs_confirmation:
                symbol = "!"
            elif _float_value(status.state.get("retry_count")) > 0:
                symbol = "↻"
            else:
                symbol = "●"
        elif phase_set and phase_set.issubset(completed):
            symbol = "✓"
        else:
            symbol = "○"
        lines.append(f"{symbol} {label}")
    return lines


def _current_phase_index(status: JobStatus) -> int:
    current_phase = _present_phase(status.current_phase)
    if current_phase in PIPELINE_PHASES:
        return PIPELINE_PHASES.index(current_phase)
    return max(0, min(int(status.current_phase_idx), len(PIPELINE_PHASES) - 1))


def _present_phase(phase: str) -> str:
    if phase == "human_confirmation":
        return "requirements_review"
    return phase


def _workflow_line(symbol: str, role: str, index: int | None) -> str:
    label = (
        _PHASE_LABELS.get(PIPELINE_PHASES[index], PIPELINE_PHASES[index])
        if index is not None
        else "-"
    )
    return f"{symbol} {role:<12} {label}".rstrip()


def _runtime_monitor_lines(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    lines: list[str] = []
    if "cpu_percent" in value:
        lines.append(f"{'CPU':<13}{value['cpu_percent']}%")
    if "memory_gb" in value:
        lines.append(f"{'Memory':<13}{value['memory_gb']} GB")
    if "disk_free_gb" in value:
        lines.append(f"{'Disk':<13}{value['disk_free_gb']} GB free")
    if "events_done" in value or "events_total" in value:
        done = value.get("events_done", 0)
        total = value.get("events_total", "?")
        lines.append(f"{'Events':<13}{done} / {total}")
    if "speed" in value:
        lines.append(f"{'Speed':<13}{value['speed']}")
    return lines


def _simulation_summary_lines(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    lines: list[str] = []
    for key in ("Particle", "Energy", "Target", "Thickness", "Detector", "Events"):
        if key in value:
            lines.append(f"{key:<13}{value[key]}")
    return lines


def _ascii_chart_lines(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    title = str(value.get("title") or "Chart")
    bins = value.get("bins")
    if not isinstance(bins, list):
        return []
    lines = [title]
    for label, raw_ratio in bins[:8]:
        ratio = max(0.0, min(1.0, _float_value(raw_ratio)))
        filled = max(1, round(ratio * 10)) if ratio > 0 else 0
        bar = "█" * filled
        lines.append(f"{str(label):<6}{bar}")
    return lines


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


def _detail_fields(detail: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in detail.split(";"):
        key, sep, value = item.strip().partition("=")
        if sep:
            fields[key.strip().lower()] = value.strip()
    return fields


def _tool_state(tool: Any) -> str:
    if tool is None:
        return "MISSING"
    configured = bool(_value(tool, "configured", False))
    available = bool(_value(tool, "available", False))
    detail = str(_value(tool, "detail", "")).lower()
    if available and "missing" not in detail:
        return "READY"
    if configured or available:
        return "PARTIAL"
    return "MISSING"


def _status_label(value: str) -> str:
    lowered = value.lower()
    if lowered in {"ok", "ready", "found"}:
        return "READY"
    if lowered in {"missing", "failed"}:
        return "MISSING"
    if lowered in {"unknown", "unset"}:
        return lowered.upper()
    return value.upper()


def _format_bytes(value: Any) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        size = 0.0
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f} MB"
    if size >= 1_000:
        return f"{size / 1_000:.1f} KB"
    return f"{int(size)} B"


def _clip_table_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


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
