"""Parse simulation results and create output packages.

Fix 4: Reads from the canonical output directory
       (08_data_packages/g4_output_package/).
       Validates all 5 required files exist.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from agent_core.config.workspace import get_output_dir
from agent_core.graph.state import RadiationAgentState

# Required output files for Geant4 data contract
G4_REQUIRED_FILES = (
    "g4_summary.json",
    "edep_3d.csv",
    "dose_3d.csv",
    "event_table.csv",
    "provenance.json",
)


def _read_csv_safe(path: Path) -> list[dict]:
    """Read a CSV file safely, returning empty list on error."""
    if not path.exists():
        return []
    try:
        with path.open(newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _check_physics_basics(edep_rows: list[dict], dose_rows: list[dict]) -> dict:
    """Basic physics sanity: count NaN, Inf, negative values."""
    checks = {"negative_energy_count": 0, "nan_count": 0, "total_events_recorded": 0}
    for row in edep_rows:
        for v in row.values():
            try:
                fv = float(v)
                if math.isnan(fv) or math.isinf(fv):
                    checks["nan_count"] += 1
                elif fv < 0:
                    checks["negative_energy_count"] += 1
            except (ValueError, TypeError):
                pass
    for row in dose_rows:
        for v in row.values():
            try:
                fv = float(v)
                if math.isnan(fv) or math.isinf(fv):
                    checks["nan_count"] += 1
                elif fv < 0:
                    checks["negative_energy_count"] += 1
            except (ValueError, TypeError):
                pass
    checks["total_events_recorded"] = len(edep_rows)
    return checks


async def parse_simulation_results(state: RadiationAgentState) -> dict:
    """Parse simulation outputs into structured data packages."""
    job_id = state.get("job_id", "unknown")
    scope = state.get("task_spec", {}).get("simulation_scope", [])

    results: dict = {"geant4": None, "tcad": None, "spice": None}
    g4_output_package: dict = {}

    if "geant4" in scope:
        output_dir = get_output_dir(job_id)

        # Check which required files exist
        file_status = {name: (output_dir / name).exists() for name in G4_REQUIRED_FILES}

        # Read CSV data for physics checks
        edep_rows = _read_csv_safe(output_dir / "edep_3d.csv")
        dose_rows = _read_csv_safe(output_dir / "dose_3d.csv")

        # Read summary and provenance if available
        provenance: dict = {}
        if file_status["g4_summary.json"]:
            try:
                _g4_summary = json.loads((output_dir / "g4_summary.json").read_text())
            except (json.JSONDecodeError, OSError):
                pass
        if file_status["provenance.json"]:
            try:
                provenance = json.loads((output_dir / "provenance.json").read_text())
            except (json.JSONDecodeError, OSError):
                pass

        # Build physics checks from actual data
        checks = _check_physics_basics(edep_rows, dose_rows)

        g4_output_package = {
            "schema_version": "g4_output_v1",
            "simulation_id": job_id,
            "particle": state.get("simulation_ir", {})
            .get("g4_config", {})
            .get("particle_source", {}),
            "geometry": state.get("simulation_ir", {})
            .get("g4_config", {})
            .get("geometry", {}),
            "outputs": {
                "edep": {
                    "file": "edep_3d.csv",
                    "unit": "MeV",
                    "exists": file_status["edep_3d.csv"],
                    "rows": len(edep_rows),
                },
                "dose": {
                    "file": "dose_3d.csv",
                    "unit": "Gy",
                    "exists": file_status["dose_3d.csv"],
                    "rows": len(dose_rows),
                },
                "event_table": {
                    "file": "event_table.csv",
                    "exists": file_status["event_table.csv"],
                },
                "g4_summary": {
                    "file": "g4_summary.json",
                    "exists": file_status["g4_summary.json"],
                },
                "provenance": {
                    "file": "provenance.json",
                    "exists": file_status["provenance.json"],
                },
            },
            "checks": checks,
            "output_dir": str(output_dir),
            "all_required_files_present": all(file_status.values()),
            "provenance": provenance,
        }

        # Ensure output package dir exists and write summary
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_file = output_dir / "g4_summary.json"
        if not file_status["g4_summary.json"]:
            # Write a generated summary if the C++ code didn't produce one
            summary_file.write_text(
                json.dumps(g4_output_package, indent=2, ensure_ascii=False)
            )

        results["geant4"] = g4_output_package

    return {
        "simulation_results": results,
        "g4_output_package": g4_output_package,
        "current_node": "parse_simulation_results",
    }
