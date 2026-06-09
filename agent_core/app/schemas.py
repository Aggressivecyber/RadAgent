from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

PipelinePhase = Literal[
    "prepare_workspace",
    "context",
    "task_planning",
    "g4_modeling",
    "human_confirmation",
    "g4_codegen",
    "patch",
    "gate",
    "artifact",
    "report",
]


class RadAgentEvent(BaseModel):
    event_type: str
    status: Literal["info", "running", "success", "warning", "error"] = "info"
    summary: str = ""
    phase: str = ""
    job_id: str = ""
    run_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobStatus(BaseModel):
    job_id: str = ""
    user_query: str = ""
    status: str = "idle"
    current_phase: str = ""
    current_phase_idx: int = 0
    completed_phases: list[str] = Field(default_factory=list)
    execution_mode: str = "strict"
    run_mode: str = "strict"
    workspace_root: str = ""
    job_workspace: str = ""
    needs_confirmation: bool = False
    key_statuses: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    message: str
    intent: str = ""
    intent_detail: str = ""
    events: list[RadAgentEvent] = Field(default_factory=list)


class PhaseResult(BaseModel):
    phase: str
    success: bool
    state_delta: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus
    events: list[RadAgentEvent] = Field(default_factory=list)


class ArtifactSummary(BaseModel):
    job_id: str
    path: str
    stage: str = ""
    kind: str = ""
    size_bytes: int = 0
    sha256: str = ""
    mime_type: str = ""
    created_at: str = ""


class ArtifactContent(BaseModel):
    path: str
    exists: bool
    kind: Literal["text", "json", "binary", "missing"] = "missing"
    text: str = ""
    json_data: Any | None = None
    size_bytes: int = 0
    truncated: bool = False


class BuildResult(BaseModel):
    success: bool
    configure: dict[str, Any] = Field(default_factory=dict)
    build: dict[str, Any] = Field(default_factory=dict)
    executable_path: str = ""
    errors: str = ""


class SimulationResult(BaseModel):
    success: bool
    output_dir: str = ""
    log: str = ""
    errors: str = ""
