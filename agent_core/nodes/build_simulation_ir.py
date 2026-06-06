"""Build Simulation IR from TaskSpec."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agent_core.config.workspace import get_job_dir, get_output_dir
from agent_core.graph.state import RadiationAgentState


async def build_simulation_ir(state: RadiationAgentState) -> dict:
    """Build Simulation Intermediate Representation from TaskSpec."""
    task_spec = state.get("task_spec", {})
    job_id = state.get("job_id", "unknown")
    scope = task_spec.get("simulation_scope", [])

    task_spec_hash = hashlib.sha256(
        json.dumps(task_spec, sort_keys=True).encode()
    ).hexdigest()[:12]

    sim_ir: dict[str, Any] = {
        "simulation_id": job_id,
        "task_spec_hash": task_spec_hash,
        "g4_config": None,
        "tcad_config": None,
        "spice_config": None,
        "mapping_chain": None,
        "unit_registry": {},
    }

    # Build G4 config if in scope
    if "geant4" in scope:
        particle = task_spec.get("particle", {})
        target = task_spec.get("target", {})
        sim_ir["g4_config"] = {
            "geometry": {
                "target_material": target.get("material", "Si"),
                "dimensions_um": target.get("size_um", [1000.0, 1000.0, 300.0]),
                "world_size_um": [2000.0, 2000.0, 1000.0],
            },
            "particle_source": {
                "type": particle.get("type", "proton"),
                "energy_MeV": particle.get("energy_MeV", 10.0),
                "direction": particle.get("direction", [0, 0, 1]),
                "events": particle.get("events", 1000),
            },
            "physics_list": task_spec.get("physics_options", {}).get(
                "physics_list", "FTFP_BERT"
            ),
            "scoring": {
                "edep": "energy_deposition" in task_spec.get("outputs", []),
                "dose": "dose_distribution" in task_spec.get("outputs", []),
                "voxel_size_um": [50.0, 50.0, 50.0],
                "output_format": "csv",
            },
            "run_config": {
                "threads": 1,
                "output_dir": str(get_output_dir(job_id)),
            },
        }
        sim_ir["unit_registry"]["energy"] = "MeV"
        sim_ir["unit_registry"]["length"] = "um"
        sim_ir["unit_registry"]["dose"] = "Gy"

    # Build TCAD config stub
    if "tcad" in scope:
        sim_ir["tcad_config"] = {
            "simulation_type": "device",
            "device_structure": None,
            "mesh_config": None,
            "physics_models": None,
            "defect_model": None,
            "bias_conditions": None,
        }

    # Build SPICE config stub
    if "spice" in scope:
        sim_ir["spice_config"] = {
            "circuit_type": None,
            "models": [],
            "stimulus": [],
            "analysis": {},
        }

    # Build mapping chain if multi-scope
    if len(scope) > 1:
        sim_ir["mapping_chain"] = {
            "g4_to_tcad": {"mapping_method": "parameterized", "parameters": {}},
            "tcad_to_spice": {"mapping_method": "PWL_current_source", "parameters": {}},
        }

    # Save simulation IR
    job_dir = get_job_dir(job_id)
    ir_file = job_dir / "03_simulation_ir" / "simulation_ir.json"
    ir_file.write_text(json.dumps(sim_ir, indent=2, ensure_ascii=False))

    return {"simulation_ir": sim_ir, "current_node": "build_simulation_ir"}
