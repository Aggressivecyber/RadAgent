from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IntentType = Literal[
    "smalltalk",
    "help",
    "status_query",
    "capability_query",
    "simulation_request",
    "simulation_edit",
    "simulation_continue",
    "human_confirmation_response",
    "command",
    "artifact_query",
    "unknown",
]


class IntentResult(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    routing_reason: str
    normalized_user_query: str
    requires_job: bool = False
    requires_simulation_pipeline: bool = False
    requires_clarification: bool = False
    extracted_command: str | None = None
