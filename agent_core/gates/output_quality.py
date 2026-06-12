"""Quality checks for Geant4 output contract artifacts."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUIRED_G4_OUTPUTS = (
    "g4_summary.json",
    "edep_3d.csv",
    "dose_3d.csv",
    "event_table.csv",
    "provenance.json",
)

_SMOKE_ERROR_PATTERNS = (
    re.compile(r"COMMAND NOT FOUND", re.IGNORECASE),
    re.compile(r"Batch is interrupted", re.IGNORECASE),
    re.compile(r"DumpToFile\s*:\s*Unknown option", re.IGNORECASE),
    re.compile(r"ERROR\s*:\s*DumpToFile", re.IGNORECASE),
    re.compile(r"parameter value .* is not listed in the candidate List", re.IGNORECASE),
    re.compile(r"FatalException", re.IGNORECASE),
    re.compile(r"Segmentation fault", re.IGNORECASE),
    re.compile(r"core dumped", re.IGNORECASE),
)


@dataclass
class OutputQualityReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors


def inspect_g4_output_quality(
    output_dir: Path,
    *,
    smoke_result: dict[str, Any] | None = None,
    expected_events: int | None = None,
) -> OutputQualityReport:
    """Validate that output artifacts contain useful smoke-simulation data."""

    report = OutputQualityReport()
    if not output_dir.is_dir():
        report.errors.append("No simulation output directory")
        return report

    missing = [name for name in REQUIRED_G4_OUTPUTS if not (output_dir / name).is_file()]
    report.metrics["missing_outputs"] = missing
    if missing:
        report.errors.append(f"Missing output contract files: {', '.join(missing)}")

    summary = _read_json(output_dir / "g4_summary.json")
    summary_events = _positive_int(summary.get("events_requested"))
    if summary_events is not None:
        report.metrics["events_requested"] = summary_events
    required_events = _positive_int(expected_events) or summary_events
    if required_events is not None:
        report.metrics["expected_events"] = required_events
    if (
        expected_events is not None
        and summary_events is not None
        and summary_events != expected_events
    ):
        report.errors.append(
            f"g4_summary.json records {summary_events} events; expected {expected_events}"
        )

    _inspect_event_table(output_dir / "event_table.csv", required_events, report)
    _inspect_quantity_csv(output_dir / "edep_3d.csv", "edep_MeV", report)
    _inspect_quantity_csv(output_dir / "dose_3d.csv", "dose_Gy", report)
    _inspect_smoke_errors(smoke_result, report)
    return report


def detect_smoke_runtime_errors(stderr: str) -> list[str]:
    """Return stable Geant4/runtime stderr patterns that invalidate a smoke run."""
    if not stderr.strip():
        return []
    return [
        pattern.pattern
        for pattern in _SMOKE_ERROR_PATTERNS
        if pattern.search(stderr)
    ]


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _inspect_event_table(
    path: Path,
    expected_events: int | None,
    report: OutputQualityReport,
) -> None:
    if not path.is_file():
        return
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = set(reader.fieldnames or [])
            required = {"EventID", "edep_MeV", "dose_Gy"}
            missing_columns = sorted(required - fieldnames)
            rows = list(reader)
    except OSError as exc:
        report.errors.append(f"event_table.csv unreadable: {exc}")
        return

    report.metrics["event_table_rows"] = len(rows)
    if missing_columns:
        report.errors.append(
            "event_table.csv missing required columns: " + ", ".join(missing_columns)
        )
    if not rows:
        report.errors.append("event_table.csv has no event rows")
        return
    if expected_events is not None and len(rows) < expected_events:
        report.errors.append(
            f"event_table.csv has {len(rows)} event rows; expected at least {expected_events}"
        )

    nonzero_events = 0
    for index, row in enumerate(rows, start=1):
        edep = _finite_float(row.get("edep_MeV"))
        dose = _finite_float(row.get("dose_Gy"))
        if edep is None:
            report.errors.append(f"event_table.csv row {index}: invalid edep_MeV")
            continue
        if dose is None:
            report.errors.append(f"event_table.csv row {index}: invalid dose_Gy")
            continue
        if edep < 0.0 or dose < 0.0:
            report.errors.append(f"event_table.csv row {index}: negative edep/dose")
        if edep > 0.0 or dose > 0.0:
            nonzero_events += 1
    report.metrics["event_table_nonzero_rows"] = nonzero_events
    if nonzero_events == 0:
        # The canary for physics actually being scored. A zero-edep event table
        # almost always means the scoring/output wiring is broken (not a build
        # bug), so give the model an actionable root-cause hint rather than a
        # generic message.
        report.errors.append(
            "event_table.csv has no non-zero edep_MeV rows — energy is not being "
            "scored into any region. Verify: (1) the ScoringManager is created in "
            "the DetectorConstruction CONSTRUCTOR, not in ConstructSDandField() "
            "(ActionInitialization::Build() runs before ConstructSDandField and "
            "must fetch a non-null ScoringManager for EventAction/SteppingAction); "
            "(2) the sensitive detector records under its componentId, matching "
            "ScoringManager::RegisterRegionScoring; (3) the primary particle "
            "actually intersects a sensitive volume."
        )


def _inspect_quantity_csv(path: Path, quantity: str, report: OutputQualityReport) -> None:
    if not path.is_file():
        return
    name = path.name
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = set(reader.fieldnames or [])
            rows = list(reader)
    except OSError as exc:
        report.errors.append(f"{name} unreadable: {exc}")
        return

    coordinate_groups = (("x", "x_mm"), ("y", "y_mm"), ("z", "z_mm"))
    missing_coordinates = [
        "/".join(group)
        for group in coordinate_groups
        if not any(col in fieldnames for col in group)
    ]
    missing_columns = sorted({quantity} - fieldnames) + missing_coordinates
    if missing_columns:
        report.errors.append(f"{name} missing required columns: {', '.join(missing_columns)}")
    if not rows:
        report.errors.append(f"{name} has no data rows")
        return

    nonzero = 0
    total = 0.0
    invalid_count = 0
    negative_count = 0
    for row in rows:
        value = _finite_float(row.get(quantity))
        if value is None:
            invalid_count += 1
            continue
        if value < 0.0:
            negative_count += 1
        if value > 0.0:
            nonzero += 1
            total += value

    metric_prefix = name.removesuffix(".csv")
    report.metrics[f"{metric_prefix}_rows"] = len(rows)
    report.metrics[f"{metric_prefix}_nonzero_rows"] = nonzero
    report.metrics[f"{metric_prefix}_positive_sum"] = total
    if invalid_count:
        report.errors.append(f"{name} has {invalid_count} invalid {quantity} values")
    if negative_count:
        report.errors.append(f"{name} has {negative_count} negative {quantity} values")
    if nonzero == 0:
        report.errors.append(f"{name} has no non-zero {quantity} bins")


def _inspect_smoke_errors(
    smoke_result: dict[str, Any] | None,
    report: OutputQualityReport,
) -> None:
    if not smoke_result:
        return
    stderr = str(smoke_result.get("errors") or "")
    if not stderr.strip():
        return
    runtime_errors = detect_smoke_runtime_errors(stderr)
    if runtime_errors:
        report.errors.append(f"Smoke simulation stderr contains: {runtime_errors[0]}")
        return
    report.warnings.append("Smoke simulation wrote stderr; review smoke_simulation_result.json")


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed
