from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class MemoryItem(BaseModel):
    """A compact fact that can be injected into copilot context."""

    source: Literal["run", "project", "evidence"] = "run"
    key: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvidenceSummary(BaseModel):
    """Evidence and credibility artifacts available for a job."""

    evidence_map_path: str = ""
    credibility_report_path: str = ""
    credibility_level: str = ""
    gate_status: str = ""
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowContext(BaseModel):
    """Current workflow state exposed to the copilot."""

    job_id: str = ""
    run_id: str = ""
    user_query: str = ""
    status: str = "idle"
    current_phase: str = ""
    current_phase_idx: int = 0
    completed_phases: list[str] = Field(default_factory=list)
    needs_confirmation: bool = False
    key_statuses: dict[str, Any] = Field(default_factory=dict)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    gate_results: list[dict[str, Any]] = Field(default_factory=list)
    confirmation: dict[str, Any] = Field(default_factory=dict)
    evidence: EvidenceSummary = Field(default_factory=EvidenceSummary)
    memory: list[MemoryItem] = Field(default_factory=list)


class CopilotCommand(BaseModel):
    """A workflow command suggested or executed by the copilot."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    risk: Literal["read", "safe", "write"] = "read"
    status: Literal["executed", "pending", "rejected"] = "pending"
    summary: str = ""


class CopilotResponse(BaseModel):
    """Response returned to frontends for workflow-aware chat."""

    message: str
    commands: list[CopilotCommand] = Field(default_factory=list)
    context: WorkflowContext = Field(default_factory=WorkflowContext)
    events: list[Any] = Field(default_factory=list)
