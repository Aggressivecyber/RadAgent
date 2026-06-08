"""Structured event schemas for RadAgent observability."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent_core.observability.redaction import sanitize


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ObservabilityEvent:
    job_id: str
    event_type: str
    status: str = "info"
    phase: str = ""
    layer: str = ""
    module_name: str = ""
    gate_name: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    run_id: str = ""
    summary: str = ""
    duration_ms: float | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return sanitize(
            {
                "event_id": self.event_id,
                "timestamp": self.timestamp,
                "job_id": self.job_id,
                "run_id": self.run_id,
                "span_id": self.span_id,
                "parent_span_id": self.parent_span_id,
                "event_type": self.event_type,
                "status": self.status,
                "phase": self.phase,
                "layer": self.layer,
                "module_name": self.module_name,
                "gate_name": self.gate_name,
                "summary": self.summary,
                "duration_ms": self.duration_ms,
                "metrics": self.metrics,
                "artifacts": self.artifacts,
                "errors": self.errors,
                "warnings": self.warnings,
                "details": self.details,
            }
        )
