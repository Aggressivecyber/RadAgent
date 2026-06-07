"""G4 Codegen Subgraph I/O — loads IR and persists generated code."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir

from .schemas import G4CodegenSubgraphState


async def load_model_ir(state: G4CodegenSubgraphState) -> dict[str, Any]:
    """Load g4_model_ir from file path into state."""
    ir_path = state.get("g4_model_ir_path", "")
    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text())
    else:
        model_ir = {}

    return {
        "g4_model_ir": model_ir,
        "errors": [],
        "retry_count": 0,
    }


async def persist_codegen_output(state: G4CodegenSubgraphState) -> dict[str, Any]:
    """Persist codegen output to disk and generate output paths."""
    job_id = state.get("job_id", "unknown")
    job_dir = get_job_dir(job_id)
    g4_dir = job_dir / "05_geant4"
    g4_dir.mkdir(parents=True, exist_ok=True)

    # Save code module plan
    code_modules = state.get("code_modules", [])
    plan_path = g4_dir / "config" / "code_module_plan.json"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps({"modules": code_modules}, indent=2))

    # Save proposed patch
    proposed_patch = state.get("proposed_patch", {})
    patch_path = job_dir / "09_validation" / "proposed_patch.json"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(json.dumps(proposed_patch, indent=2, ensure_ascii=False))

    # Check if we have generated code
    has_code = bool(proposed_patch.get("changed_files"))
    status = "passed" if has_code else "failed"

    return {
        "code_module_plan_path": str(plan_path),
        "proposed_patch_path": str(patch_path),
        "generated_code_dir": str(g4_dir),
        "g4_codegen_status": status,
    }
