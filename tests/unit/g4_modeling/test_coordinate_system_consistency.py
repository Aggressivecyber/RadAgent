"""Unit tests for coordinate system consistency validator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec, PlacementSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.validators.coordinate_consistency_validator import (
    CoordinateConsistencyValidator,
)


def _make_ir_with_placements(positions: dict[str, list[float]]) -> G4ModelIR:
    components = [
        ComponentSpec(
            component_id="world",
            display_name="World",
            component_type="world",
            geometry_type="box",
            dimensions={"dx": 5000.0, "dy": 5000.0, "dz": 5000.0},
            material_id="air",
            source_evidence=["user_spec"],
        ),
    ]
    for cid, pos in positions.items():
        components.append(
            ComponentSpec(
                component_id=cid,
                display_name=cid,
                component_type="layer",
                geometry_type="box",
                dimensions={"dx": 100.0, "dy": 100.0, "dz": 10.0},
                material_id="silicon",
                mother_volume="world",
                placement=PlacementSpec(position=pos),
                source_evidence=["user_spec"],
            ),
        )
    mat = MaterialSpec(
        material_id="air",
        name="Air",
        classification="nist",
        nist_name="G4_AIR",
        density_g_cm3=0.001225,
        source_evidence=["nist"],
    )
    si = MaterialSpec(
        material_id="silicon",
        name="Silicon",
        classification="nist",
        nist_name="G4_Si",
        density_g_cm3=2.33,
        source_evidence=["nist"],
    )
    return G4ModelIR(
        model_ir_id="test",
        job_id="job",
        components=components,
        materials=[mat, si],
    )


class TestCoordinateConsistencyValidator:
    """Test CoordinateConsistencyValidator."""

    def test_consistent_placements_pass(self):
        ir = _make_ir_with_placements(
            {
                "sensor": [0.0, 0.0, 0.0],
                "shield": [0.0, 0.0, 200.0],
            }
        )
        validator = CoordinateConsistencyValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Unexpected errors: {errors}"

    def test_empty_components_pass(self):
        ir = G4ModelIR(model_ir_id="test", job_id="job")
        validator = CoordinateConsistencyValidator()
        passed, errors = validator.validate(ir)
        assert passed

    def test_origin_centered_placements(self):
        """Placements at origin should be valid."""
        ir = _make_ir_with_placements(
            {
                "layer1": [0.0, 0.0, 0.0],
            }
        )
        validator = CoordinateConsistencyValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"
