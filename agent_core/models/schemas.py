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


class ModelCallRequest(BaseModel):
    task: ModelTask
    tier: ModelTier
    system_prompt: str
    user_prompt: str
    response_format: Literal["text", "json"] = "text"
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ModelCallResult(BaseModel):
    task: ModelTask
    tier: ModelTier
    provider: ModelProvider
    model_name: str
    content: str
    parsed_json: dict[str, Any] | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float | None = None
    error: str | None = None
