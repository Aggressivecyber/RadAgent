"""CodePatch schema — represents a code modification proposed by the Agent."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Zone = Literal["green", "yellow", "red"]
RiskLevel = Literal["low", "medium", "high", "critical"]
ChangeType = Literal["create", "modify", "delete"]

# Minimum risk required per zone
_ZONE_MIN_RISK: dict[str, int] = {"green": 0, "yellow": 1, "red": 2}
_RISK_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}


class ChangedFile(BaseModel):
    """A single file change within a patch."""

    model_config = {"extra": "forbid"}

    path: str
    zone: Zone
    diff_content: str = ""
    new_content: str = ""

    @model_validator(mode="after")
    def _validate_content(self) -> ChangedFile:
        if self.zone == "red" and not self.diff_content and not self.new_content:
            raise ValueError("Red-zone files must include diff_content or new_content")
        return self


class CodePatch(BaseModel):
    """A code modification proposed by the Agent."""

    model_config = {"extra": "forbid"}

    patch_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    job_id: str
    description: str
    change_type: ChangeType
    risk_level: RiskLevel
    changed_files: list[ChangedFile]
    test_plan: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    rollback_possible: bool = True
    metadata: dict | None = None

    @field_validator("risk_level")
    @classmethod
    def risk_must_cover_zones(cls, v: RiskLevel, info) -> RiskLevel:
        """Ensure risk level is sufficient for the most sensitive file zone."""
        changed_files = info.data.get("changed_files", [])
        if not changed_files:
            return v
        max_zone = max(
            (_ZONE_MIN_RISK.get(f.zone if isinstance(f, ChangedFile) else f.get("zone", "green"), 0)
             for f in changed_files),
            default=0,
        )
        if _RISK_ORDER[v] < max_zone:
            allowed = [k for k, ord_ in _RISK_ORDER.items() if ord_ >= max_zone]
            raise ValueError(
                f"risk_level '{v}' too low for file zones present; choose from {allowed}"
            )
        return v

    def apply(self) -> dict[str, str]:
        """Return a preview of what would change without writing to disk."""
        preview: dict[str, str] = {}
        for f in self.changed_files:
            if self.change_type == "create":
                preview[f.path] = f.new_content
            elif self.change_type == "delete":
                preview[f.path] = "<DELETE>"
            else:
                preview[f.path] = f.diff_content or f.new_content
        return preview
