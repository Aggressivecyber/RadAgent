from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ModelTier(StrEnum):
    LITE = "lite"
    PRO = "pro"
    MAX = "max"


class ModelTask(StrEnum):
    INTENT_ROUTING = "intent_routing"
    SIMPLE_EXTRACTION = "simple_extraction"
    TASK_PLANNING = "task_planning"
    CONTEXT_SUMMARY = "context_summary"
    MODEL_READINESS = "model_readiness"
    G4_MODELING = "g4_modeling"
    HUMAN_CONFIRMATION = "human_confirmation"
    CODEGEN = "codegen"
    GATE_EXPLANATION = "gate_explanation"
    CREDIBILITY_ASSESSMENT = "credibility_assessment"
    FINAL_REVIEW = "final_review"
    FAILURE_DIAGNOSIS = "failure_diagnosis"
    SIMULATION_BRIEFING = "simulation_briefing"


class ModelProvider(StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    MOCK = "mock"


class ModelProfile(BaseModel):
    tier: ModelTier
    provider: ModelProvider
    model_name: str
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_s: float = 60
    max_retries: int = 2
    temperature: float = 0.0
    max_tokens: int = 4096
    context_window_tokens: int = 1_000_000


class ModelCallRequest(BaseModel):
    task: ModelTask
    tier: ModelTier
    system_prompt: str
    user_prompt: str
    response_format: Literal["text", "json"] = "text"
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Native OpenAI-style function calling (agentic loops). When ``messages``
    # is provided it replaces the system/user pair (full multi-turn control).
    # When ``tools`` is provided the provider may return ``tool_calls`` instead
    # of plain content.
    messages: list[dict[str, Any]] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None


class ModelCallResult(BaseModel):
    task: ModelTask
    tier: ModelTier
    provider: ModelProvider
    model_name: str
    content: str
    parsed_json: Any | None = None
    reasoning_content: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = None
    error: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    finish_reason: str = ""
