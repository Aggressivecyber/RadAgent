"""Plan geometry strategy for each component."""

from __future__ import annotations

import json
from typing import Any

from agent_core.g4_codegen.schemas import GeometryStrategyPlan
from agent_core.workspace.paths import STAGE_CODEGEN

EXTERNAL_EXTENSIONS = {".step", ".stp", ".stl", ".ply", ".gdml"}


def plan_geometry_strategy(
    g4_model_ir: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Plan geometry strategy for each component.

    Identifies CAD/GDML files, checks existence, and assigns strategies.
    Does NOT perform real CAD conversion.
    """
    components = g4_model_ir.get("components", [])
    strategies: dict[str, str] = {}
    external_files: list[dict[str, Any]] = []
    warnings: list[str] = []

    for comp in components:
        cid = comp.get("component_id", "unknown")
        geo = comp.get("geometry", {})
        geo_type = geo.get("type", "primitive")

        if geo_type in ("cad", "gdml", "step", "stl", "ply"):
            strategies[cid] = "external_cad_required"
            file_path = geo.get("file_path", "")
            file_exists = False
            if file_path:
                from pathlib import Path as FilePath

                file_exists = FilePath(file_path).exists()

            external_files.append(
                {
                    "component_id": cid,
                    "path": file_path,
                    "source_type": geo_type,
                    "exists": file_exists,
                    "status": "exists" if file_exists else "missing",
                    "action": "ok" if file_exists else "clarification_required",
                }
            )
        elif geo_type == "parameterized":
            strategies[cid] = "parameterized"
        elif geo_type == "replica":
            strategies[cid] = "replica"
        elif geo_type == "boolean":
            strategies[cid] = "boolean"
        elif geo_type == "assembly":
            strategies[cid] = "assembly"
        else:
            strategies[cid] = "primitive"

    plan = GeometryStrategyPlan(
        global_strategy="agent_generated_geometry",
        component_strategies=strategies,
        requires_external_files=external_files,
        unsupported_features=[],
        warnings=warnings,
    )

    # Persist
    from agent_core.workspace.io import get_job_dir

    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)

    plan_path = codegen_dir / "geometry_strategy_plan.json"
    plan_path.write_text(json.dumps(plan.model_dump(), indent=2, ensure_ascii=False))

    return plan.model_dump()
