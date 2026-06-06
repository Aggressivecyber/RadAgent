"""Plan simulation strategy based on task spec and RAG context."""

from __future__ import annotations

import json
from pathlib import Path

from agent_core.graph.state import RadiationAgentState


async def plan_simulation(state: RadiationAgentState) -> dict:
    """Create a simulation execution plan."""
    task_spec = state.get("task_spec", {})
    sim_ir = state.get("simulation_ir", {})
    scope = task_spec.get("simulation_scope", [])
    job_id = state.get("job_id", "unknown")

    plan = {
        "job_id": job_id,
        "phases": [],
        "estimated_duration": "unknown",
        "required_tools": [],
    }

    if "geant4" in scope:
        g4_config = sim_ir.get("g4_config", {})
        events = g4_config.get("particle_source", {}).get("events", 1000)
        plan["phases"].append(
            {
                "name": "geant4_simulation",
                "steps": [
                    "generate_detector_construction",
                    "generate_physics_list",
                    "generate_primary_generator",
                    "generate_scoring",
                    "generate_cmake_build",
                    "build_project",
                    "run_smoke_test",
                    "run_production",
                ],
                "events": events,
                "smoke_events": min(10, events),
            }
        )
        plan["required_tools"].extend(["cmake", "g++", "geant4"])

    # Save plan
    job_dir = Path("simulation_workspace/jobs") / job_id
    plan_dir = job_dir / "04_generated_code"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan_file = plan_dir / "simulation_plan.json"
    plan_file.write_text(json.dumps(plan, indent=2, ensure_ascii=False))

    return {"simulation_plan": plan, "current_node": "plan_simulation"}
