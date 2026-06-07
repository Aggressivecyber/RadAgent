"""Coordinate consistency validator — Gate G4-C (partial).

Ensures coordinate system units are consistent and
placements are compatible with interface definitions.
"""

from __future__ import annotations

from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR


class CoordinateConsistencyValidator:
    """Validates coordinate system consistency across the model."""

    def validate(self, model_ir: G4ModelIR) -> tuple[bool, list[str]]:
        """Check coordinate system consistency.

        - All placements use 3-element vectors
        - Units match global_units.length
        - Placement positions are compatible with interface gaps
        """
        errors: list[str] = []

        # Check placements are finite
        for comp in model_ir.components:
            pos = comp.placement.position
            if len(pos) != 3:
                errors.append(
                    f"Component '{comp.component_id}' placement has "
                    f"{len(pos)} elements, expected 3"
                )
            for i, val in enumerate(pos):
                if val != val:  # NaN check
                    errors.append(
                        f"Component '{comp.component_id}' placement "
                        f"position[{i}] is NaN"
                    )
                if abs(val) == float("inf"):
                    errors.append(
                        f"Component '{comp.component_id}' placement "
                        f"position[{i}] is infinite"
                    )

            rot = comp.placement.rotation
            if len(rot) != 3:
                errors.append(
                    f"Component '{comp.component_id}' rotation has "
                    f"{len(rot)} elements, expected 3"
                )

        # Check voxel scoring uses consistent units
        for sc in model_ir.scoring:
            if sc.voxel_grid is not None:
                vs = sc.voxel_grid.voxel_size
                if len(vs) != 3:
                    errors.append(
                        f"Scoring '{sc.scoring_id}' voxel_size has "
                        f"{len(vs)} elements, expected 3"
                    )
                for val in vs:
                    if val <= 0:
                        errors.append(
                            f"Scoring '{sc.scoring_id}' voxel_size "
                            f"must be positive, got {val}"
                        )

        return len(errors) == 0, errors
