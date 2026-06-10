"""Pydantic models for revision sandbox workflow state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RevisionRunState = Literal["created", "running", "completed", "failed"]


class RevisionRequest(BaseModel):
    """A persisted request to revise one job in an isolated sandbox."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    job_id: str
    user_request: str
    workspace_root: str
    base_generated_code_dir: str
    revision_dir: str
    baseline_dir: str
    candidate_project_dir: str
    proposed_patch_path: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RevisionStatus(BaseModel):
    """Current execution status for a revision sandbox."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    job_id: str
    status: RevisionRunState = "created"
    revision_dir: str
    baseline_dir: str
    candidate_project_dir: str
    proposed_patch_path: str = ""
    patch_status: str = "not_requested"
    patch_review_path: str = ""
    applied_patch_path: str = ""
    errors: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RevisionSummary(BaseModel):
    """Compact revision view for listing and UI surfaces."""

    model_config = ConfigDict(extra="forbid")

    revision_id: str
    job_id: str
    user_request: str
    status: RevisionRunState
    revision_dir: str
    candidate_project_dir: str
    patch_status: str = "not_requested"
    errors: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_request_status(
        cls,
        request: RevisionRequest,
        status: RevisionStatus,
    ) -> RevisionSummary:
        """Build a summary from the persisted request and status records."""
        return cls(
            revision_id=request.revision_id,
            job_id=request.job_id,
            user_request=request.user_request,
            status=status.status,
            revision_dir=request.revision_dir,
            candidate_project_dir=request.candidate_project_dir,
            patch_status=status.patch_status,
            errors=list(status.errors),
            created_at=request.created_at,
            updated_at=status.updated_at,
        )
