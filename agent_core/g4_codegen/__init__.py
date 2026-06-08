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
    """Persist codegen output to disk and generate output paths.

    NOTE: This is a legacy function kept for backward compatibility.
    The graph uses graph_nodes.persist_codegen_output_node instead.
    """
    import warnings

    warnings.warn(
        "Use graph_nodes.persist_codegen_output_node instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    job_id = state.get("job_id", "unknown")
    job_dir = get_job_dir(job_id)
    # P0-6: Target must be 08_geant4 (not 05_geant4)
    g4_dir = job_dir / "08_geant4"
    g4_dir.mkdir(parents=True, exist_ok=True)

    # Save proposed patch to 06_codegen
    codegen_dir = job_dir / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)

    proposed_patch = state.get("proposed_patch", {})
    patch_path = codegen_dir / "proposed_patch.json"
    patch_path.write_text(json.dumps(proposed_patch, indent=2, ensure_ascii=False))

    has_code = bool(proposed_patch.get("changed_files"))
    status = "passed" if has_code else "failed"

    return {
        "proposed_patch_path": str(patch_path),
        "generated_code_dir": str(g4_dir),
        "g4_codegen_status": status,
    }
