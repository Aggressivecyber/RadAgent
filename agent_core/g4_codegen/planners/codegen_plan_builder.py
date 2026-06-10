"""Build overall codegen plan from G4ModelIR."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.g4_codegen.schemas import CodegenPlan
from agent_core.workspace.paths import STAGE_CODEGEN

CORE_MODULES = [
    "simulation_core",
    "beam_physics",
    "runtime_app",
]

MODULE_ORDER = list(CORE_MODULES)


def detect_scenario_type(g4_model_ir: dict[str, Any]) -> str:
    """Detect simulation scenario type from model IR."""
    components = g4_model_ir.get("components", [])
    comp_types = {c.get("component_type", "") for c in components}

    if any("detector" in ct.lower() or "sensor" in ct.lower() for ct in comp_types):
        return "semiconductor_detector"
    if any("shield" in ct.lower() or "absorb" in ct.lower() for ct in comp_types):
        return "shielding"
    if len(components) > 5:
        return "complex_detector"
    return "simple_geometry"


def build_codegen_plan(
    g4_model_ir: dict[str, Any],
    job_id: str,
    run_mode: str = "strict",
) -> dict[str, Any]:
    """Build codegen plan from G4ModelIR.

    Determines scenario type, required modules, and module order.
    Persists plan to disk and returns the plan dict.
    """
    scenario_type = detect_scenario_type(g4_model_ir)

    # Check for unsupported features
    unsupported: list[str] = []
    components = g4_model_ir.get("components", [])
    for comp in components:
        geo = comp.get("geometry", {})
        geo_type = geo.get("type", "")
        if geo_type in ("cad", "gdml", "step", "stl", "ply"):
            unsupported.append(f"CAD/GDML geometry: {comp.get('component_id', '')}")

    plan = CodegenPlan(
        scenario_type=scenario_type,
        required_modules=list(CORE_MODULES),
        module_order=list(MODULE_ORDER),
        unsupported_features=unsupported,
        requires_human_confirmation=len(unsupported) > 0,
        rationale=f"Scenario: {scenario_type}, {len(components)} components",
    )

    # Persist
    codegen_dir = Path(job_id) / STAGE_CODEGEN if "/" in job_id else Path(job_id)
    if not codegen_dir.is_absolute():
        from agent_core.workspace.io import get_job_dir

        codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)

    plan_path = codegen_dir / "codegen_plan.json"
    plan_path.write_text(json.dumps(plan.model_dump(), indent=2, ensure_ascii=False))

    return plan.model_dump()
