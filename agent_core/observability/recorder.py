"""Append-only job-scoped observability recorder."""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_core.observability.events import ObservabilityEvent


def _job_log_dir(job_id: str) -> Path:
    from agent_core.config.workspace import get_job_dir

    log_dir = get_job_dir(job_id) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def record_event(
    *,
    job_id: str | None,
    event_type: str,
    status: str = "info",
    phase: str = "",
    layer: str = "",
    module_name: str = "",
    gate_name: str = "",
    summary: str = "",
    duration_ms: float | None = None,
    metrics: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    details: dict[str, Any] | None = None,
    span_id: str = "",
    parent_span_id: str = "",
    run_id: str = "",
) -> dict[str, Any] | None:
    """Append one structured event to ``logs/events.jsonl``.

    Logging is best-effort: failures never break the pipeline being observed.
    """
    if not job_id:
        return None
    try:
        event = ObservabilityEvent(
            job_id=job_id,
            event_type=event_type,
            status=status,
            phase=phase,
            layer=layer,
            module_name=module_name,
            gate_name=gate_name,
            summary=summary,
            duration_ms=duration_ms,
            metrics=metrics or {},
            artifacts=artifacts or [],
            errors=errors or [],
            warnings=warnings or [],
            details=details or {},
            span_id=span_id,
            parent_span_id=parent_span_id,
            run_id=run_id,
        )
        payload = event.to_dict()
        log_dir = _job_log_dir(job_id)
        with (log_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        _append_trace_event(log_dir, payload)
        return payload
    except Exception:
        return None


def start_span(
    *,
    job_id: str | None,
    name: str,
    phase: str = "",
    layer: str = "",
    module_name: str = "",
    gate_name: str = "",
    parent_span_id: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    span_id = uuid4().hex
    start = time.monotonic()
    record_event(
        job_id=job_id,
        event_type="span_start",
        status="running",
        phase=phase,
        layer=layer,
        module_name=module_name,
        gate_name=gate_name,
        summary=name,
        details=details or {},
        span_id=span_id,
        parent_span_id=parent_span_id,
    )
    return {"span_id": span_id, "start": start, "name": name, "parent_span_id": parent_span_id}


def end_span(
    *,
    job_id: str | None,
    span: dict[str, Any],
    status: str,
    phase: str = "",
    layer: str = "",
    module_name: str = "",
    gate_name: str = "",
    summary: str = "",
    metrics: dict[str, Any] | None = None,
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    duration_ms = (time.monotonic() - float(span.get("start", time.monotonic()))) * 1000
    record_event(
        job_id=job_id,
        event_type="span_end",
        status=status,
        phase=phase,
        layer=layer,
        module_name=module_name,
        gate_name=gate_name,
        summary=summary or str(span.get("name", "")),
        duration_ms=duration_ms,
        metrics=metrics or {},
        errors=errors or [],
        warnings=warnings or [],
        details=details or {},
        span_id=str(span.get("span_id", "")),
        parent_span_id=str(span.get("parent_span_id", "")),
    )


@contextmanager
def observed_span(
    *,
    job_id: str | None,
    name: str,
    phase: str = "",
    layer: str = "",
    module_name: str = "",
    gate_name: str = "",
    details: dict[str, Any] | None = None,
):
    span = start_span(
        job_id=job_id,
        name=name,
        phase=phase,
        layer=layer,
        module_name=module_name,
        gate_name=gate_name,
        details=details,
    )
    try:
        yield span
    except Exception as exc:
        end_span(
            job_id=job_id,
            span=span,
            status="error",
            phase=phase,
            layer=layer,
            module_name=module_name,
            gate_name=gate_name,
            errors=[str(exc)],
        )
        raise
    else:
        end_span(
            job_id=job_id,
            span=span,
            status="success",
            phase=phase,
            layer=layer,
            module_name=module_name,
            gate_name=gate_name,
        )


def write_failure_bundle(
    *,
    job_id: str | None,
    status: str,
    phase: str = "",
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    details: dict[str, Any] | None = None,
) -> Path | None:
    """Write a compact failure bundle for quick debugging."""
    if not job_id:
        return None
    try:
        log_dir = _job_log_dir(job_id)
        recent_events = _read_recent_events(log_dir / "events.jsonl", limit=80)
        bundle = {
            "job_id": job_id,
            "status": status,
            "phase": phase,
            "errors": errors or [],
            "warnings": warnings or [],
            "artifacts": artifacts or [],
            "details": details or {},
            "recent_events": recent_events,
        }
        path = log_dir / "failure_bundle.json"
        path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
    except Exception:
        return None


def _append_trace_event(log_dir: Path, event: dict[str, Any]) -> None:
    trace_path = log_dir / "trace.json"
    if trace_path.exists():
        try:
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            trace = {"events": []}
    else:
        trace = {"events": []}
    trace.setdefault("events", []).append(event)
    trace_path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_recent_events(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
