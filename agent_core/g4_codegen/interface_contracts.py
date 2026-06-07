"""Interface contracts — CAD/GDML, G4→TCAD, TCAD→SPICE placeholders."""

from __future__ import annotations

import json
from typing import Any


def build_interface_contracts(
    g4_model_ir: dict[str, Any],
    geometry_strategy_plan: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Build interface contracts for cross-system interfaces.

    Creates placeholder contracts for:
    1. CAD/GDML geometry input
    2. G4→TCAD data transfer
    3. TCAD→SPICE data transfer

    Does NOT perform any real conversion.
    """
    cad_gdml: list[dict[str, Any]] = []
    g4_to_tcad: list[dict[str, Any]] = []
    tcad_to_spice: list[dict[str, Any]] = []

    # CAD/GDML contracts from geometry strategy
    external_files = geometry_strategy_plan.get("requires_external_files", [])
    for ext in external_files:
        cad_gdml.append({
            "contract_id": f"cad_or_gdml_{ext.get('component_id', 'unknown')}",
            "source_path": ext.get("path", ""),
            "source_type": ext.get("source_type", "unknown"),
            "conversion_required": True,
            "conversion_status": "not_implemented",
            "action": "clarification_required_or_future_stage",
        })

    # If no CAD/GDML files, still add a placeholder
    if not cad_gdml:
        cad_gdml.append({
            "contract_id": "cad_or_gdml_geometry_placeholder",
            "source_path": "",
            "source_type": "none",
            "conversion_required": False,
            "conversion_status": "not_applicable",
            "action": "no_cad_gdml_input_detected",
        })

    # G4→TCAD placeholder
    g4_to_tcad.append({
        "contract_id": "g4_to_tcad_damage_v1",
        "source_artifact": "10_data_packages/g4_output_package/dose_3d.csv",
        "target_parameter": "tcad.defects.trap_density",
        "conversion_required": True,
        "conversion_status": "future_stage_pending_confirmation",
    })

    # TCAD→SPICE placeholder
    tcad_to_spice.append({
        "contract_id": "tcad_to_spice_iv_v1",
        "source_artifact": "tcad/output/iv_curve.csv",
        "target_parameter": "spice.device.sensor.leakage_current",
        "conversion_required": True,
        "conversion_status": "future_stage",
    })

    contracts = {
        "cad_gdml": cad_gdml,
        "g4_to_tcad": g4_to_tcad,
        "tcad_to_spice": tcad_to_spice,
    }

    # Persist
    from agent_core.config.workspace import get_job_dir
    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)

    contracts_path = codegen_dir / "interface_contracts.json"
    contracts_path.write_text(json.dumps(contracts, indent=2, ensure_ascii=False))

    return contracts
