"""Gate result and report schemas for pipeline quality gates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class GateResult(BaseModel):
    """Result of a single quality gate check."""

    gate_id: int = Field(ge=0, le=11)
    gate_name: str
    passed: bool
    severity: Literal["pass", "warning", "fail", "block", "skipped"]
    message: str
    details: dict | None = None
    remediation: str | None = None
    retry_node: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class GateReport(BaseModel):
    """Aggregated report of all gate results for a pipeline job."""

    job_id: str
    total_gates: int = 12
    results: list[GateResult]

    @computed_field
    @property
    def overall_passed(self) -> bool:
        return all(
            r.severity in ("pass", "warning", "skipped") for r in self.results
        )

    @computed_field
    @property
    def summary(self) -> str:
        passed = sum(1 for r in self.results if r.severity == "pass")
        warned = sum(1 for r in self.results if r.severity == "warning")
        failed = sum(1 for r in self.results if r.severity in ("fail", "block"))
        skipped = sum(1 for r in self.results if r.severity == "skipped")
        status = "PASS" if self.overall_passed else "FAIL"
        return f"{status}: {passed} passed, {warned} warnings, {skipped} skipped, {failed} failed"


def create_gate_result(
    gate_id: int,
    gate_name: str,
    passed: bool,
    *,
    severity: Literal["pass", "warning", "fail", "block", "skipped"] | None = None,
    message: str = "",
    details: dict | None = None,
    remediation: str | None = None,
    retry_node: str | None = None,
) -> GateResult:
    """Create a GateResult with auto-derived severity when omitted."""
    if severity is None:
        severity = "pass" if passed else "fail"
    return GateResult(
        gate_id=gate_id,
        gate_name=gate_name,
        passed=passed,
        severity=severity,
        message=message,
        details=details,
        remediation=remediation,
        retry_node=retry_node,
    )


def create_gate_report(job_id: str, results: list[GateResult]) -> GateReport:
    """Create a GateReport for a given job."""
    return GateReport(job_id=job_id, results=results)
