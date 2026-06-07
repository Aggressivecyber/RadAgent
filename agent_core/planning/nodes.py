"""Task Planning Subgraph nodes.

Converts user query into a structured task specification.
Only "geant4" scope is supported in this phase.
TCAD/SPICE/full_chain are recorded as reserved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir

from .schemas import TaskPlanningState


def _get_task_dir(job_id: str) -> Path:
    return get_job_dir(job_id) / "02_task_spec"


# Reserved scopes that are not yet implemented
_RESERVED_SCOPES = {"tcad", "spice", "geant4_to_tcad", "tcad_to_spice", "full_chain"}


async def parse_task(state: TaskPlanningState) -> dict[str, Any]:
    """Parse user query into a task specification."""
    user_query = state.get("user_query", "")
    job_id = state.get("job_id", "unknown")
    task_dir = _get_task_dir(job_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    # Determine simulation scope from query
    scope: list[str] = ["geant4"]  # Default

    query_lower = user_query.lower()
    if "tcad" in query_lower and "spice" in query_lower:
        scope = ["geant4", "tcad", "spice", "full_chain"]
    elif "tcad" in query_lower:
        scope = ["geant4", "tcad"]
    elif "spice" in query_lower:
        scope = ["geant4", "spice"]

    # Parse particle info
    particle: dict[str, Any] = {}
    if "proton" in query_lower or "质子" in user_query:
        particle = {"type": "proton", "pdg_code": 2212}
    elif "gamma" in query_lower or "gamma" in query_lower:
        particle = {"type": "gamma", "pdg_code": 22}
    elif "electron" in query_lower or "电子" in user_query:
        particle = {"type": "electron", "pdg_code": 11}

    # Parse energy
    import re

    energy_match = re.search(r"(\d+(?:\.\d+)?)\s*(MeV|keV|GeV)", user_query)
    energy_value = float(energy_match.group(1)) if energy_match else 10.0
    energy_unit = energy_match.group(2) if energy_match else "MeV"

    task_spec: dict[str, Any] = {
        "job_id": job_id,
        "user_query": user_query,
        "simulation_scope": scope,
        "particle": particle,
        "energy": {"value": energy_value, "unit": energy_unit},
        "modeling_mode": "realistic",
    }

    # Validate
    if not particle:
        errors.append("Cannot determine particle type from query")

    return {
        "task_spec": task_spec,
        "task_spec_errors": errors,
        "simulation_scope": scope,
    }


async def validate_task_spec(state: TaskPlanningState) -> dict[str, Any]:
    """Validate the parsed task spec."""
    task_spec = state.get("task_spec", {})
    errors = list(state.get("task_spec_errors", []))

    if not task_spec.get("simulation_scope"):
        errors.append("No simulation scope determined")

    scope = task_spec.get("simulation_scope", [])
    reserved_in_scope = [s for s in scope if s in _RESERVED_SCOPES]

    if reserved_in_scope:
        # Record but don't fail — geant4 parts can proceed
        pass

    if not errors:
        status = "passed"
    else:
        status = "failed"

    return {
        "task_spec_errors": errors,
        "task_planning_status": status,
    }


async def save_task_spec(state: TaskPlanningState) -> dict[str, Any]:
    """Save task spec and simulation scope to disk."""
    job_id = state.get("job_id", "unknown")
    task_dir = _get_task_dir(job_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    task_spec = state.get("task_spec", {})
    scope = state.get("simulation_scope", ["geant4"])

    # Save task spec
    ts_path = task_dir / "task_spec.json"
    ts_path.write_text(json.dumps(task_spec, indent=2, ensure_ascii=False))

    # Save simulation scope
    scope_path = task_dir / "simulation_scope.json"
    scope_path.write_text(json.dumps({"scope": scope}, indent=2))

    return {
        "task_spec_path": str(ts_path),
    }
