from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agent_core.models.schemas import ModelTier


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
    errors: list[str] = Field(default_factory=list)


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


class ModelTierConfig(BaseModel):
    tier: ModelTier
    model_name: str
    base_url: str = ""
    api_key_env: str = "RADAGENT_API_KEY"
    api_key_configured: bool = False
    timeout_s: float = 60
    max_retries: int = 2
    temperature: float = 0.0
    max_tokens: int = 4096
    thinking_default: bool = False


class ModelConfigView(BaseModel):
    env_path: str
    default_api_key_env: str = "RADAGENT_API_KEY"
    tiers: dict[str, ModelTierConfig] = Field(default_factory=dict)


class ModelConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str = "RADAGENT_API_KEY"
    lite_model: str | None = None
    pro_model: str | None = None
    max_model: str | None = None
    lite_timeout_s: float | None = None
    pro_timeout_s: float | None = None
    max_timeout_s: float | None = None
    lite_max_tokens: int | None = None
    pro_max_tokens: int | None = None
    max_max_tokens: int | None = None
