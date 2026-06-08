"""CodePatch schema — represents a code modification proposed by the Agent.

MVP-1 uses ``json_file_replacement`` exclusively: each changed file specifies
its full new content via ``new_content``.  Empty ``diff_content`` is NOT a
valid diff — it simply means the patch is using JSON replacement mode.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

PatchType = Literal["json_file_replacement"]
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
    operation: Literal["create_or_replace"] = "create_or_replace"
    zone: Zone
    diff_content: str = ""  # Deprecated: MVP-1 uses json_file_replacement only
    new_content: str = ""

    @model_validator(mode="after")
    def _validate_content(self) -> ChangedFile:
        if not self.new_content and not self.diff_content:
            raise ValueError(f"File '{self.path}' must have new_content or diff_content")
        return self


class CodePatch(BaseModel):
    """A code modification proposed by the Agent."""

    model_config = {"extra": "forbid"}

    patch_type: PatchType = "json_file_replacement"
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
    def risk_must_cover_zones(cls, v: RiskLevel, info: Any) -> RiskLevel:
        """Ensure risk level is sufficient for the most sensitive file zone."""
        changed_files = info.data.get("changed_files", [])
        if not changed_files:
            return v
        max_zone = max(
            (
                _ZONE_MIN_RISK.get(
                    f.zone if isinstance(f, ChangedFile) else f.get("zone", "green"), 0
                )
                for f in changed_files
            ),
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
            if f.new_content:
                preview[f.path] = f.new_content
            elif f.diff_content:
                preview[f.path] = f.diff_content
            else:
                preview[f.path] = "<DELETE>"
        return preview
