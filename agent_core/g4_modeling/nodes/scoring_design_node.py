"""Scoring design node — creates scoring specs from model IR.

Deterministic node: defines voxel/region scoring based on sensitive
detectors and component roles.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def scoring_design_node(state: RadiationAgentState) -> dict[str, Any]:
    """Design scoring configuration for the model.

    Reads: g4_model_ir (components, sensitive_detectors, coordinate_system)
    Writes: g4_model_ir.scoring
    """
    model_ir_dict = state.get("g4_model_ir", {})

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
    from agent_core.g4_modeling.schemas.scoring_spec import (
        RegionScore,
        ScoringSpec,
        VoxelGrid,
    )

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    scoring: list[ScoringSpec] = []

    # 1. Per-sensitive-region scoring (edep + dose)
    for sd in model_ir.sensitive_detectors:
        for comp_id in sd.linked_component_ids:
            comp = model_ir.component_by_id(comp_id)
            if comp is None:
                continue

            # Region scoring for edep
            edep_scoring = ScoringSpec(
                scoring_id=f"{comp_id}_edep",
                scoring_type="region",
                quantities=["edep_MeV"],
                region_scores=[
                    RegionScore(
                        region_component_id=comp_id,
                        quantity="edep_MeV",
                    )
                ],
                output_format="csv",
                source_evidence=[
                    f"Auto-generated: region edep scoring for {comp_id}",
                ],
            )
            scoring.append(edep_scoring)

            # Region scoring for dose (if component has dose role)
            if "dose_scoring_region" in comp.roles:
                dose_scoring = ScoringSpec(
                    scoring_id=f"{comp_id}_dose",
                    scoring_type="region",
                    quantities=["dose_Gy"],
                    region_scores=[
                        RegionScore(
                            region_component_id=comp_id,
                            quantity="dose_Gy",
                        )
                    ],
                    output_format="csv",
                    source_evidence=[
                        f"Auto-generated: region dose scoring for {comp_id}",
                    ],
                )
                scoring.append(dose_scoring)

    # 2. Voxel scoring for 3D dose maps (if component has 3d_dose_map role)
    for comp in model_ir.components:
        if "3d_dose_map" in comp.roles:
            dims = comp.dimensions
            dx = dims.get("dx", 100.0)
            dy = dims.get("dy", 100.0)
            dz = dims.get("dz", 100.0)

            # Voxel size: ~1/10 of each dimension, at least 1 um
            voxel_dx = max(1.0, round(dx / 10.0, 1))
            voxel_dy = max(1.0, round(dy / 10.0, 1))
            voxel_dz = max(1.0, round(dz / 10.0, 1))

            voxel_scoring = ScoringSpec(
                scoring_id=f"{comp.component_id}_voxel_dose",
                scoring_type="voxel",
                quantities=["dose_Gy"],
                voxel_grid=VoxelGrid(
                    target_component_id=comp.component_id,
                    voxel_size=[voxel_dx, voxel_dy, voxel_dz],
                ),
                output_format="csv",
                source_evidence=[
                    f"Auto-generated: voxel dose map for {comp.component_id}, "
                    f"voxel_size=[{voxel_dx}, {voxel_dy}, {voxel_dz}] um",
                ],
            )
            scoring.append(voxel_scoring)

    # 3. Event table scoring (if any sensitive detectors exist)
    if model_ir.sensitive_detectors:
        all_sensitive_ids: list[str] = []
        for sd in model_ir.sensitive_detectors:
            all_sensitive_ids.extend(sd.linked_component_ids)

        event_table = ScoringSpec(
            scoring_id="event_table",
            scoring_type="region",
            quantities=["edep_MeV", "event_id", "track_id"],
            region_scores=[
                RegionScore(
                    region_component_id=cid,
                    quantity="edep_MeV",
                )
                for cid in all_sensitive_ids
            ],
            output_format="csv",
            source_evidence=[
                "Auto-generated: event table for all sensitive components",
            ],
        )
        scoring.append(event_table)

    model_ir.scoring = scoring

    model_ir.ledger.add_entry(
        node_name="scoring_design_node",
        action="create",
        target_id="scoring",
        description=f"Created {len(scoring)} scoring configurations: "
        f"{[s.scoring_id for s in scoring]}",
        modified_fields=["scoring"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "scoring_design_node",
    }
