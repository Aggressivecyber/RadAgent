"""Source definition node — configures particle source from requirements.

Deterministic node: configures particle gun or GPS based on task spec.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def source_definition_node(state: RadiationAgentState) -> dict[str, Any]:
    """Configure particle source from task spec and evidence.

    Reads: g4_model_ir (components, coordinate_system), task_spec
    Writes: g4_model_ir.sources
    """
    model_ir_dict = state.get("g4_model_ir", {})
    task_spec = state.get("task_spec", {})

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
    from agent_core.g4_modeling.schemas.source_spec import (
        BeamProfile,
        EnergySpec,
        SourceSpec,
    )

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Extract source parameters from task_spec
    particle = task_spec.get("particle", {})
    particle_type = particle.get("type", "proton")
    energy_mev = particle.get("energy_MeV", 10.0)
    direction = particle.get("direction", [0, 0, 1])
    events = particle.get("events", 1000)

    # Determine beam starting position (above target)
    z_offset = -500.0  # Default: 500 um above target
    for comp in model_ir.components:
        if comp.component_type != "world" and comp.mother_volume:
            dims = comp.dimensions
            dz = dims.get("dz", 0)
            pos_z = comp.placement.position[2]
            top_edge = pos_z + dz
            if top_edge > z_offset:
                z_offset = -(top_edge + 500.0)

    # Determine generator type
    generator_type: Literal["gun", "gps"] = "gun"
    sigma_pos = None
    sigma_dir = None
    surface_shape: Literal["circle", "rectangle", "point"] = "point"

    energy = EnergySpec(
        value=energy_mev,
        unit="MeV",
        distribution="mono",
    )

    beam = BeamProfile(
        position=[0.0, 0.0, z_offset],
        direction=direction,
        sigma_position_um=sigma_pos,
        sigma_direction_rad=sigma_dir,
        surface_shape=surface_shape,
    )

    source = SourceSpec(
        source_id="primary_source",
        particle_type=particle_type,
        energy=energy,
        beam=beam,
        generator_type=generator_type,
        events=events,
        source_evidence=[
            f"task_spec: particle={particle_type}, "
            f"energy={energy_mev} MeV, direction={direction}"
        ],
    )

    model_ir.sources = [source]

    model_ir.ledger.add_entry(
        node_name="source_definition_node",
        action="create",
        target_id="primary_source",
        description=f"Configured {particle_type} source at {energy_mev} MeV, "
        f"{events} events, generator={generator_type}",
        modified_fields=["sources"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "current_node": "source_definition_node",
    }
