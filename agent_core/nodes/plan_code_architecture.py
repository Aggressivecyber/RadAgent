"""Plan code architecture for the generated simulation project."""

from __future__ import annotations

from typing import Any

from agent_core.graph.state import RadiationAgentState


async def plan_code_architecture(state: RadiationAgentState) -> dict:
    """Plan the architecture of generated simulation code."""
    task_spec = state.get("task_spec", {})
    scope = task_spec.get("simulation_scope", [])

    arch_plan: dict[str, Any] = {"modules": [], "file_map": {}, "dependencies": []}

    if "geant4" in scope:
        arch_plan["modules"] = [
            {"name": "DetectorConstruction", "purpose": "Define geometry and materials"},
            {"name": "PhysicsList", "purpose": "Configure physics processes"},
            {"name": "PrimaryGeneratorAction", "purpose": "Define particle source"},
            {"name": "EventAction", "purpose": "Collect event-level data"},
            {"name": "RunAction", "purpose": "Manage run initialization and output"},
            {"name": "SteppingAction", "purpose": "Score energy deposition per step"},
        ]
        arch_plan["file_map"] = {
            "src/DetectorConstruction.cc": "DetectorConstruction implementation",
            "src/PhysicsList.cc": "PhysicsList implementation",
            "src/PrimaryGeneratorAction.cc": "PrimaryGeneratorAction implementation",
            "src/EventAction.cc": "EventAction implementation",
            "src/RunAction.cc": "RunAction implementation",
            "src/SteppingAction.cc": "SteppingAction implementation",
            "include/DetectorConstruction.hh": "DetectorConstruction header",
            "include/PhysicsList.hh": "PhysicsList header",
            "include/PrimaryGeneratorAction.hh": "PrimaryGeneratorAction header",
            "include/EventAction.hh": "EventAction header",
            "include/RunAction.hh": "RunAction header",
            "include/SteppingAction.hh": "SteppingAction header",
            "geant4_sim.cc": "Main entry point",
            "CMakeLists.txt": "Build configuration",
        }
        arch_plan["dependencies"] = ["Geant4::Granular"]

    return {
        "code_architecture_plan": arch_plan,
        "current_node": "plan_code_architecture",
    }
