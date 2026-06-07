"""Sensitive detector node — defines SDs for scoring components.

Deterministic node: creates SD specs for components marked as sensitive.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.g4_modeling.schemas.sensitive_detector_spec import (
    HitFieldSpec,
    SensitiveDetectorSpec,
)
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)

# Standard hit fields for radiation scoring
_STANDARD_HIT_FIELDS: list[HitFieldSpec] = [
    HitFieldSpec(name="event_id", dtype="int"),
    HitFieldSpec(name="track_id", dtype="int"),
    HitFieldSpec(name="particle", dtype="int", unit="G4ParticleDefinition PDG encoding"),
    HitFieldSpec(name="edep_MeV", dtype="float", unit="MeV"),
    HitFieldSpec(name="x_um", dtype="float", unit="um"),
    HitFieldSpec(name="y_um", dtype="float", unit="um"),
    HitFieldSpec(name="z_um", dtype="float", unit="um"),
    HitFieldSpec(name="time_s", dtype="float", unit="s"),
]


async def sensitive_detector_node(state: RadiationAgentState) -> dict[str, Any]:
    """Define sensitive detectors for sensitive components.

    Reads: g4_model_ir (components with sensitive=True, scoring)
    Writes: g4_model_ir.sensitive_detectors
    """
    model_ir_dict = state.get("g4_model_ir", {})

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Find sensitive components
    sensitive_components = [c for c in model_ir.components if c.sensitive]
    if not sensitive_components:
        # Auto-detect: make components with scoring roles sensitive
        sensitive_components = [
            c for c in model_ir.components
            if any(
                role in c.roles
                for role in ("dose_scoring_region", "edep_region", "sensitive")
            )
        ]

    # Create SD specs
    sds: list[SensitiveDetectorSpec] = []
    for comp in sensitive_components:
        sd_name = f"{comp.component_id}_SD"
        # Replace non-alphanumeric chars for C++ class name
        class_name = "".join(
            word.capitalize() for word in sd_name.replace("-", "_").split("_")
        ) + "SensitiveDetector"

        # Link scoring IDs that target this component
        linked_scoring = [
            s.scoring_id for s in model_ir.scoring
            if (
                s.voxel_grid and s.voxel_grid.target_component_id == comp.component_id
            ) or any(
                rs.region_component_id == comp.component_id
                for rs in s.region_scores
            )
        ]

        sd = SensitiveDetectorSpec(
            sd_id=sd_name.lower(),
            name=class_name,
            linked_component_ids=[comp.component_id],
            scoring_ids=linked_scoring,
            collection_name=f"{comp.component_id}_Hits",
            hit_fields=list(_STANDARD_HIT_FIELDS),
        )
        sds.append(sd)

    model_ir.sensitive_detectors = sds

    model_ir.ledger.add_entry(
        node_name="sensitive_detector_node",
        action="create",
        target_id="sensitive_detectors",
        description=f"Created {len(sds)} sensitive detectors for: "
        f"{[c.component_id for c in sensitive_components]}",
        modified_fields=["sensitive_detectors"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "sensitive_detector_node",
    }
