"""Interface contracts for codegen-visible external boundaries."""

from __future__ import annotations

import json
from typing import Any

from agent_core.workspace.paths import STAGE_CODEGEN


def build_interface_contracts(
    g4_model_ir: dict[str, Any],
    geometry_strategy_plan: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Build interface contracts from current model requirements.

    The codegen graph should only pass contracts that correspond to actual
    model inputs or explicitly requested downstream boundaries. It does not
    create speculative TCAD/SPICE handoff contracts.
    """
    cad_gdml: list[dict[str, Any]] = []

    # CAD/GDML contracts from geometry strategy
    external_files = geometry_strategy_plan.get("requires_external_files", [])
    for ext in external_files:
        cad_gdml.append(
            {
                "contract_id": f"cad_or_gdml_{ext.get('component_id', 'unknown')}",
                "source_path": ext.get("path", ""),
                "source_type": ext.get("source_type", "unknown"),
                "conversion_required": True,
                "conversion_status": "not_implemented",
                "action": "clarification_required_or_future_stage",
            }
        )

    contracts = {
        "cad_gdml": cad_gdml,
        "downstream_handoffs": [],
        "metadata": {
            "source": "g4_model_ir_and_geometry_strategy",
            "note": (
                "No TCAD/SPICE handoff contract is emitted unless a future "
                "modeling stage adds explicit IR fields for that boundary."
            ),
        },
    }

    # Persist
    from agent_core.workspace.io import get_job_dir

    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)

    contracts_path = codegen_dir / "interface_contracts.json"
    contracts_path.write_text(json.dumps(contracts, indent=2, ensure_ascii=False))

    return contracts
