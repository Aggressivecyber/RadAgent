"""Model scope guard node — prevents pipeline from proceeding with insufficient info.

Checks whether evidence and requirements are sufficient for realistic modeling.
If not, blocks the pipeline with a clear explanation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState
from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_MODEL_IR

logger = logging.getLogger(__name__)


async def model_scope_guard_node(state: RadiationAgentState) -> dict[str, Any]:
    """Judge whether the model can be constructed with available information.

    Reads: g4_model_ir (with evidence and target_system)
    Writes: model_scope_guard_result
    Persists: model IR stage scope_guard.json
    """
    model_ir_dict = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "")

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    missing_dimensions: list[str] = []
    warnings: list[str] = []
    action = "proceed"

    # Check evidence availability per dimension
    evidence = model_ir.evidence
    if evidence is not None:
        dim_checks = {
            "geometry": evidence.geometry,
            "materials": evidence.materials,
            "source": evidence.source,
            "physics": evidence.physics,
            "scoring": evidence.scoring,
        }
        for dim, items in dim_checks.items():
            if not items:
                missing_dimensions.append(dim)

        # Check evidence decision
        if evidence.evidence_decision == "block_no_context":
            action = "block"
            missing_dimensions.extend(["all — context blocked"])
    else:
        missing_dimensions.append("all — no evidence pack")
        action = "block"

    # Check target system description
    if not model_ir.target_system.strip():
        warnings.append("target_system is empty — requirements may be incomplete")

    # Determine final action
    if missing_dimensions and action != "block":
        # Critical dimensions missing?
        critical = {"geometry", "materials", "source"}
        if critical.issubset(set(missing_dimensions)):
            action = "block"
        else:
            action = "proceed_with_warnings"

    guard_result = {
        "action": action,
        "missing_dimensions": missing_dimensions,
        "warnings": warnings,
        "message": (
            f"Scope guard: {action}. Missing dimensions: {missing_dimensions}. Warnings: {warnings}"
        ),
    }

    # Record ledger
    model_ir.ledger.add_entry(
        node_name="model_scope_guard_node",
        action="validate",
        target_id=model_ir.model_ir_id,
        description=f"Scope guard result: {action}",
        warnings=warnings,
    )

    # Persist
    if job_id:
        model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        guard_file = model_ir_dir / "scope_guard.json"
        guard_file.write_text(json.dumps(guard_result, indent=2, ensure_ascii=False))

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "model_scope_guard_result": guard_result,
        "current_node": "model_scope_guard_node",
    }
