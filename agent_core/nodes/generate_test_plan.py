"""Generate test plan for the simulation code."""

from __future__ import annotations

from typing import Any

from agent_core.graph.state import RadiationAgentState


async def generate_test_plan(state: RadiationAgentState) -> dict:
    """Generate a test plan for the simulation code."""
    scope = state.get("task_spec", {}).get("simulation_scope", [])
    test_plan: dict[str, list[Any]] = {"tests": []}

    if "geant4" in scope:
        test_plan["tests"] = [
            {"name": "structure_check", "description": "Verify all required files exist"},
            {"name": "cmake_configure", "description": "CMake configure succeeds"},
            {"name": "cmake_build", "description": "Build succeeds without errors"},
            {"name": "smoke_run", "description": "Run with 10 events, check output"},
            {"name": "output_not_empty", "description": "Output files are not empty"},
            {"name": "no_negative_energy", "description": "No negative energy deposition"},
            {"name": "no_nan_values", "description": "No NaN or Inf in outputs"},
        ]

    return {"test_plan": test_plan, "current_node": "generate_test_plan"}
