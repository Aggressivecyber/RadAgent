"""Validate output data contracts."""

from __future__ import annotations

import json

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState
from agent_core.validators.data_contract_validator import DataContractValidator


async def validate_data_contract(state: RadiationAgentState) -> dict:
    """Validate output data against contract schemas."""
    job_id = state.get("job_id", "unknown")
    scope = state.get("task_spec", {}).get("simulation_scope", [])
    dcv = DataContractValidator()
    contract_results = {}

    if "geant4" in scope:
        g4_pkg = state.get("g4_output_package", {})
        valid, errors = dcv.validate_g4_output(g4_pkg)
        contract_results["g4_output"] = {"valid": valid, "errors": errors}

        # Save contract check
        job_dir = get_job_dir(job_id)
        check_file = job_dir / "09_validation" / "contract_check.json"
        check_file.write_text(json.dumps(contract_results, indent=2))

    return {
        "data_contract_results": contract_results,
        "current_node": "validate_data_contract",
    }
