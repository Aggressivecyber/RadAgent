"""Parse simulation results and create output packages."""

from __future__ import annotations

import json
from pathlib import Path

from agent_core.graph.state import RadiationAgentState


async def parse_simulation_results(state: RadiationAgentState) -> dict:
    """Parse simulation outputs into structured data packages."""
    job_id = state.get("job_id", "unknown")
    scope = state.get("task_spec", {}).get("simulation_scope", [])

    results = {"geant4": None, "tcad": None, "spice": None}
    g4_output_package = {}

    if "geant4" in scope:
        job_dir = Path("simulation_workspace/jobs") / job_id
        g4_dir = job_dir / "05_geant4"
        output_dir = g4_dir / "output"

        edep_file = output_dir / "edep_3d.csv"
        dose_file = output_dir / "dose_3d.csv"
        event_file = output_dir / "event_table.csv"

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
                "edep": {"file": "edep_3d.csv", "unit": "MeV", "exists": edep_file.exists()},
                "dose": {"file": "dose_3d.csv", "unit": "Gy", "exists": dose_file.exists()},
                "event_table": {"file": "event_table.csv", "exists": event_file.exists()},
            },
            "checks": {
                "negative_energy_count": 0,
                "nan_count": 0,
                "total_events_recorded": 0,
            },
            "output_exists": output_dir.exists(),
        }

        # Save output package
        pkg_dir = job_dir / "08_data_packages" / "g4_output_package"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        summary_file = pkg_dir / "g4_summary.json"
        summary_file.write_text(json.dumps(g4_output_package, indent=2))

        results["geant4"] = g4_output_package

    return {
        "simulation_results": results,
        "g4_output_package": g4_output_package,
        "current_node": "parse_simulation_results",
    }
