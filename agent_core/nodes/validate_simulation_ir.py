"""Validate Simulation IR node."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState


async def validate_simulation_ir(state: RadiationAgentState) -> dict:
    """Validate the simulation IR against schema requirements."""
    sim_ir = state.get("simulation_ir", {})
    scope = state.get("task_spec", {}).get("simulation_scope", [])
    errors = []

    if not sim_ir.get("simulation_id"):
        errors.append("Missing simulation_id in SimulationIR")
    if not sim_ir.get("task_spec_hash"):
        errors.append("Missing task_spec_hash in SimulationIR")

    if "geant4" in scope and not sim_ir.get("g4_config"):
        errors.append("Geant4 in scope but g4_config is missing")
    if "geant4" in scope and sim_ir.get("g4_config"):
        g4 = sim_ir["g4_config"]
        if not g4.get("geometry"):
            errors.append("g4_config missing geometry")
        if not g4.get("particle_source"):
            errors.append("g4_config missing particle_source")

    return {
        "simulation_ir_errors": errors,
        "current_node": "validate_simulation_ir",
    }
