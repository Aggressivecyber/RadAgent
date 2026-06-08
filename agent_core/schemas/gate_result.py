"""Gate result and report schemas for pipeline quality gates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class GateResult(BaseModel):
    """Result of a single quality gate check.

    This schema MUST be used by all gate implementations.
    Gates output a dictionary with these fields.
    """

    gate_id: str = Field(description="Gate identifier (e.g., '0', '12', 'G4-A')")
    name: str = Field(description="Human-readable gate name")
    status: Literal["pass", "fail", "skip", "skipped", "error"] = Field(
        description="Gate status - 'skipped' is legacy, prefer 'skip'"
    )
    checked_items: list[dict] = Field(
        default_factory=list,
        description="List of items checked, each with 'item' and 'result' keys",
    )
    passed_items: list[str] = Field(
        default_factory=list, description="List of items that passed validation"
    )
    failed_items: list[str] = Field(
        default_factory=list, description="List of items that failed validation"
    )
    warnings: list[str] = Field(default_factory=list, description="List of warning messages")
    evidence: list[str] = Field(
        default_factory=list, description="Evidence URLs, file paths, or observations"
    )
    file_paths: list[str] = Field(
        default_factory=list, description="File paths involved in this gate check"
    )
    message: str = Field(description="Human-readable result message - NOT just 'OK'")
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class GateReport(BaseModel):
    """Aggregated report of all gate results for a pipeline job."""

    job_id: str
    total_gates: int = 20
    results: list[GateResult]

    @property
    def overall_passed(self) -> bool:
        return all(r.status in ("pass", "skip", "skipped") for r in self.results)

    @property
    def summary(self) -> str:
        passed = sum(1 for r in self.results if r.status == "pass")
        failed = sum(1 for r in self.results if r.status == "fail")
        # Handle both 'skip' and 'skipped' for backward compatibility
        skipped = sum(1 for r in self.results if r.status in ("skip", "skipped"))
        errored = sum(1 for r in self.results if r.status == "error")
        status = "PASS" if self.overall_passed else "FAIL"
        return f"{status}: {passed} passed, {skipped} skipped, {errored} errors, {failed} failed"


def create_gate_result(
    gate_id: str,
    name: str,
    status: Literal["pass", "fail", "skip", "error"],
    *,
    checked_items: list[dict] | None = None,
    passed_items: list[str] | None = None,
    failed_items: list[str] | None = None,
    warnings: list[str] | None = None,
    evidence: list[str] | None = None,
    file_paths: list[str] | None = None,
    message: str = "",
) -> GateResult:
    """Create a GateResult with all required fields."""
    return GateResult(
        gate_id=gate_id,
        name=name,
        status=status,
        checked_items=checked_items or [],
        passed_items=passed_items or [],
        failed_items=failed_items or [],
        warnings=warnings or [],
        evidence=evidence or [],
        file_paths=file_paths or [],
        message=message,
    )


def create_gate_report(job_id: str, results: list[GateResult]) -> GateReport:
    """Create a GateReport for a given job."""
    return GateReport(job_id=job_id, results=results)
