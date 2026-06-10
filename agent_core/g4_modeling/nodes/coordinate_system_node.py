"""Coordinate system node — defines global coordinate system.

Deterministic node: sets up coordinate system based on
beam direction and target geometry.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def coordinate_system_node(state: RadiationAgentState) -> dict[str, Any]:
    """Define the global coordinate system for the model.

    Reads: g4_model_ir (components, sources)
    Writes: g4_model_ir.coordinate_system, g4_model_ir.global_units
    """
    model_ir_dict = state.get("g4_model_ir", {})

    from agent_core.g4_modeling.schemas.g4_model_ir import (
        CoordinateSystem,
        G4ModelIR,
        GlobalUnits,
    )

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Determine coordinate system from source directions. Composite fields with
    # multiple incident angles should not be collapsed into a single beam axis.
    axis_definition = {
        "x": "sensor_width",
        "y": "sensor_length",
        "z": "beam_direction",
    }
    if model_ir.sources:
        directions = [src.beam.direction for src in model_ir.sources]
        if _has_multiple_directions(directions):
            axis_definition["z"] = "detector_depth"
            axis_definition["source_directions"] = "composite_radiation_field"
        else:
            direction = directions[0]
            # Find which axis has the largest component
            max_idx = max(range(3), key=lambda i: abs(direction[i]))
            if max_idx != 2:
                axis_definition["z"] = "sensor_height"

    model_ir.coordinate_system = CoordinateSystem(
        system="cartesian",
        origin_definition="world_center",
        axis_definition=axis_definition,
        unit=model_ir.global_units.length,
    )

    # Ensure units are set
    model_ir.global_units = GlobalUnits(
        length="um",
        energy="MeV",
        dose="Gy",
        time="s",
    )

    model_ir.ledger.add_entry(
        node_name="coordinate_system_node",
        action="modify",
        target_id=model_ir.model_ir_id,
        description=f"Set coordinate system: {model_ir.coordinate_system.system}, "
        f"origin={model_ir.coordinate_system.origin_definition}",
        modified_fields=["coordinate_system", "global_units"],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "coordinate_system": model_ir.coordinate_system.model_dump(mode="json"),
        "current_node": "coordinate_system_node",
    }


def _has_multiple_directions(directions: list[list[float]]) -> bool:
    if len(directions) < 2:
        return False
    first = _normalized_direction(directions[0])
    for direction in directions[1:]:
        if _normalized_direction(direction) != first:
            return True
    return False


def _normalized_direction(direction: list[float]) -> tuple[float, float, float]:
    return tuple(round(float(value), 6) for value in direction[:3])
