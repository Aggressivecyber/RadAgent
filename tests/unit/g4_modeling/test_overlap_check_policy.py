"""Unit tests for overlap policy validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec, PlacementSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.validators.overlap_policy_validator import (
    OverlapPolicyValidator,
)


def _world() -> ComponentSpec:
    return ComponentSpec(
        component_id="world",
        display_name="World",
        component_type="world",
        geometry_type="box",
        dimensions={"dx": 5000.0, "dy": 5000.0, "dz": 5000.0},
        material_id="air",
        source_evidence=["user_spec"],
    )


def _layer(
    cid: str,
    mother: str = "world",
    z_pos: float = 0.0,
    dz: float = 10.0,
) -> ComponentSpec:
    return ComponentSpec(
        component_id=cid,
        display_name=cid,
        component_type="layer",
        geometry_type="box",
        dimensions={"dx": 100.0, "dy": 100.0, "dz": dz},
        material_id="silicon",
        mother_volume=mother,
        placement=PlacementSpec(position=[0.0, 0.0, z_pos]),
        source_evidence=["user_spec"],
    )


def _mat(mid: str) -> MaterialSpec:
    return MaterialSpec(
        material_id=mid,
        name=mid,
        classification="nist",
        nist_name=f"G4_{mid.capitalize()}",
        density_g_cm3=2.33,
        source_evidence=["nist"],
    )


class TestOverlapPolicyValidator:
    """Test OverlapPolicyValidator."""

    def test_non_overlapping_layers_pass(self):
        """Layers well-separated should pass."""
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[
                _world(),
                _layer("layer1", z_pos=0.0, dz=10.0),
                _layer("layer2", z_pos=50.0, dz=10.0),
            ],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = OverlapPolicyValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"

    def test_overlapping_layers_detected(self):
        """Layers at same position with significant size should be flagged."""
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[
                _world(),
                _layer("layer1", z_pos=0.0, dz=50.0),
                _layer("layer2", z_pos=10.0, dz=50.0),
            ],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = OverlapPolicyValidator()
        passed, errors = validator.validate(ir)
        assert not passed

    def test_child_outside_mother_detected(self):
        """A child volume whose AABB exceeds its mother must be flagged."""
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[
                _world(),
                _layer("inside_layer", z_pos=0.0, dz=100.0),
                _layer("outside_layer", z_pos=3000.0, dz=100.0),
            ],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = OverlapPolicyValidator()
        passed, errors = validator.validate(ir)
        assert not passed
        assert any("outside mother volume" in error for error in errors)

    def test_single_child_no_overlap_issue(self):
        """Single child can't overlap with itself."""
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), _layer("only_layer")],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = OverlapPolicyValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"

    def test_empty_components_pass(self):
        ir = G4ModelIR(model_ir_id="test", job_id="job")
        validator = OverlapPolicyValidator()
        passed, errors = validator.validate(ir)
        assert passed
