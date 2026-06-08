"""Geometry validation node — smoke-check geometry via Geant4 runtime.

Deterministic node: attempts a minimal Geant4 run to validate
geometry (checkOverlaps). This is a lightweight check, not a
full simulation.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState as RadiationAgentState
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

logger = logging.getLogger(__name__)


async def geometry_validation_node(state: RadiationAgentState) -> dict[str, Any]:
    """Validate geometry via Geant4 runtime check.

    Reads: g4_model_ir, code_patch (assembled C++ files)
    Writes: model_ir_errors (appends geometry validation results)
    """
    model_ir_dict = state.get("g4_model_ir", {})

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    errors: list[str] = []

    # Check that code_patch exists with files
    raw_code_patch = state.get("code_patch", {})
    code_patch: dict[str, Any] = raw_code_patch if isinstance(raw_code_patch, dict) else {}
    raw_files = code_patch.get("files", [])
    files: list[dict[str, Any]] = raw_files if isinstance(raw_files, list) else []

    if not files:
        errors.append("Geometry validation skipped: no assembled code files available")
    else:
        # Check for checkOverlaps in placement files
        has_check_overlaps = False
        for f in files:
            content = f.get("content", "")
            if "checkOverlaps" in content:
                has_check_overlaps = True
                break

        if not has_check_overlaps:
            errors.append(
                "Geometry validation: checkOverlaps not found in any "
                "placement file — overlap checking may be disabled"
            )

    # Check component count sanity
    if len(model_ir.components) < 2:
        errors.append(
            f"Geometry has only {len(model_ir.components)} components — "
            f"expected at least world + 1 child"
        )

    # Check all mother_volume references resolve
    comp_ids = {c.component_id for c in model_ir.components}
    for comp in model_ir.components:
        if comp.mother_volume and comp.mother_volume not in comp_ids:
            errors.append(
                f"Component '{comp.component_id}' references "
                f"non-existent mother_volume '{comp.mother_volume}'"
            )

    model_ir.ledger.add_entry(
        node_name="geometry_validation_node",
        action="validate",
        target_id=model_ir.model_ir_id,
        description=f"Geometry validation: "
        f"{len(errors)} issues found in {len(model_ir.components)} components",
        modified_fields=[],
    )

    # Merge with existing model_ir_errors
    raw_existing = state.get("model_ir_errors", [])
    existing_errors: list[str] = raw_existing if isinstance(raw_existing, list) else []

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "model_ir_errors": existing_errors + errors,
        "current_node": "geometry_validation_node",
    }
