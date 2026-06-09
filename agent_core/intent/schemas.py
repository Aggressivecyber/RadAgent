from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IntentType = Literal["chat", "simulation_work"]


class IntentResult(BaseModel):
    intent: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    routing_reason: str
    normalized_user_query: str
    intent_detail: str | None = None
    requires_job: bool = False
    requires_simulation_pipeline: bool = False
    requires_clarification: bool = False
    extracted_command: str | None = None
