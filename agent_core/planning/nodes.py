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

# Keyword sets for scope detection
_GEANT4_KEYWORDS = [
    "geant4", "g4", "蒙特卡罗", "粒子输运", "辐照仿真",
    "能量沉积", "剂量分布", "monte carlo",
]
_TCAD_KEYWORDS = [
    "tcad", "sentaurus", "silvaco", "技术计算机辅助设计", "半导体器件仿真",
    "器件仿真",
]
_SPICE_KEYWORDS = [
    "spice", "ngspice", "hspice", "ltspice", "电路仿真", "网表",
]
_FULL_CHAIN_KEYWORDS = [
    "联合仿真", "全链路", "geant4到tcad", "tcad到spice", "g4到tcad",
    "全流程",
]


def detect_scope(query: str) -> list[str]:
    """Detect simulation scope from user query using keyword matching.

    Returns a deduplicated list of scope strings.
    Default is ["geant4"] if no keywords match.
    """
    q = query.lower()
    scope: list[str] = []

    if any(k in q for k in _GEANT4_KEYWORDS):
        scope.append("geant4")
    if any(k in q for k in _TCAD_KEYWORDS):
        scope.append("tcad")
    if any(k in q for k in _SPICE_KEYWORDS):
        scope.append("spice")
    if any(k in q for k in _FULL_CHAIN_KEYWORDS):
        scope.append("full_chain")

    if not scope:
        scope = ["geant4"]

    # Deduplicate while preserving order
    return list(dict.fromkeys(scope))


def validate_supported_scope(scope: list[str]) -> dict[str, Any]:
    """Check whether the detected scope is supported.

    Returns a status dict with task_planning_status set to:
      - "reserved" if TCAD/SPICE/full_chain detected
      - "passed" if pure geant4
      - "failed" for unsupported combinations
    """
    reserved = [s for s in scope if s in _RESERVED_SCOPES]

    if reserved:
        return {
            "task_planning_status": "reserved",
            "reserved_scopes": reserved,
            "termination_reason": (
                "TCAD/SPICE/full-chain simulation is reserved "
                "for later MVPs."
            ),
        }

    if scope == ["geant4"]:
        return {
            "task_planning_status": "passed",
            "reserved_scopes": [],
            "termination_reason": "",
        }

    return {
        "task_planning_status": "failed",
        "reserved_scopes": [],
        "termination_reason": f"Unsupported simulation scope: {scope}",
    }


async def parse_task(state: TaskPlanningState) -> dict[str, Any]:
    """Parse user query into a task specification."""
    user_query = state.get("user_query", "")
    job_id = state.get("job_id", "unknown")
    task_dir = _get_task_dir(job_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    # Determine simulation scope from query using keyword detection
    scope = detect_scope(user_query)
    query_lower = user_query.lower()

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
    """Validate the parsed task spec.

    Uses validate_supported_scope to check for reserved scopes.
    Sets task_planning_status to "reserved" if TCAD/SPICE detected.
    """
    task_spec = state.get("task_spec", {})
    errors = list(state.get("task_spec_errors", []))

    if not task_spec.get("simulation_scope"):
        errors.append("No simulation scope determined")

    scope = task_spec.get("simulation_scope", [])

    # Check for reserved scopes
    scope_result = validate_supported_scope(scope)
    status = scope_result["task_planning_status"]

    if status == "reserved":
        return {
            "task_spec_errors": errors,
            "task_planning_status": "reserved",
            "reserved_scopes": scope_result["reserved_scopes"],
            "termination_reason": scope_result["termination_reason"],
        }

    if errors:
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
