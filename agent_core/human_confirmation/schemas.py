"""Human confirmation schemas for RadAgent.

These models represent the human-in-the-loop confirmation process
for AI-proposed model completions.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProposedParameter(BaseModel):
    """A single proposed parameter with source tracking."""

    field_path: str
    proposed_value: Any
    unit: str | None = None
    source_type: Literal["user", "rag", "web", "default", "assumption"]
    source_ref: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    requires_confirmation: bool = True


class ProposedComponent(BaseModel):
    """A proposed component with parameters needing confirmation."""

    component_id: str
    component_type: str
    material_id: str | None = None
    geometry: dict[str, Any] = Field(default_factory=dict)
    placement: dict[str, Any] = Field(default_factory=dict)
    roles: list[str] = Field(default_factory=list)
    parameters: list[ProposedParameter] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_confirmation: bool = True


class ProposedModelCompletion(BaseModel):
    """AI-proposed model completion for user confirmation."""

    schema_version: str = "proposed_model_completion_v1"
    job_id: str
    source_query: str
    domain_profile: str = "geant4"
    proposed_components: list[ProposedComponent] = Field(default_factory=list)
    proposed_sources: list[ProposedParameter] = Field(default_factory=list)
    proposed_scoring: list[ProposedParameter] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    requires_human_confirmation: bool = True
    readiness_status: str = "draft"
    readiness_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ConfirmationQuestion(BaseModel):
    """A single question for user confirmation."""

    question_id: str
    field_path: str
    question: str
    proposed_value: Any | None = None
    unit: str | None = None
    options: list[Any] = Field(default_factory=list)
    required: bool = True
    reason: str = ""


class ConfirmationRequest(BaseModel):
    """A round of questions for user confirmation."""

    schema_version: str = "confirmation_request_v1"
    job_id: str
    round_id: int = 1
    summary_for_user: str = ""
    proposed_model_completion_path: str = ""
    questions: list[ConfirmationQuestion] = Field(default_factory=list)
    approval_options: list[str] = Field(
        default_factory=lambda: ["approve", "edit", "reject", "ask_more"]
    )


class ConfirmationEdit(BaseModel):
    """A user edit to a proposed value."""

    field_path: str
    new_value: Any
    unit: str | None = None
    reason: str | None = None


class ConfirmationResponse(BaseModel):
    """User's response to a confirmation request."""

    schema_version: str = "confirmation_response_v1"
    job_id: str
    round_id: int = 1
    user_decision: Literal["approve", "edit", "reject", "ask_more"]
    edits: list[ConfirmationEdit] = Field(default_factory=list)
    user_notes: str = ""


class ConfirmationRecord(BaseModel):
    """Complete record of human confirmation process."""

    schema_version: str = "confirmation_record_v1"
    job_id: str
    total_rounds: int = 0
    final_status: Literal["approved", "edited", "rejected", "ask_more", "failed"] = "approved"
    confirmed_fields: list[str] = Field(default_factory=list)
    edited_fields: list[str] = Field(default_factory=list)
    rejected_fields: list[str] = Field(default_factory=list)
    remaining_unconfirmed_fields: list[str] = Field(default_factory=list)
    unconfirmed_assumptions_count: int = Field(default=0, ge=0)
    confirmation_history: list[dict[str, Any]] = Field(default_factory=list)
    confirmed_model_plan_path: str | None = None
