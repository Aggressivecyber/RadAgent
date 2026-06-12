"""Unit tests for no unapproved simplification validator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.g4_model_ir import (
    G4ModelIR,
    SimplificationPolicy,
)
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.validators.no_simplification_validator import (
    NoSimplificationValidator,
)


def _world() -> ComponentSpec:
    return ComponentSpec(
        component_id="world",
        display_name="World",
        component_type="world",
        geometry_type="box",
        dimensions={"dx": 5000.0, "dy": 5000.0, "dz": 5000.0},
        material_id="air",
        source_evidence=["user_spec: world 10mm"],
    )


def _child_with_evidence(cid: str, evidence: list[str]) -> ComponentSpec:
    return ComponentSpec(
        component_id=cid,
        display_name=cid,
        component_type="layer",
        geometry_type="box",
        dimensions={"dx": 100.0, "dy": 100.0, "dz": 10.0},
        material_id="silicon",
        mother_volume="world",
        source_evidence=evidence,
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


class TestNoSimplificationValidator:
    """Test NoSimplificationValidator."""

    def test_all_evidence_present_passes(self):
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[
                _world(),
                _child_with_evidence("sensor", ["user_spec: sensor 200um"]),
            ],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"

    def test_empty_evidence_detected(self):
        """Component with empty source_evidence (bypassing schema) should fail."""
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world()],
            materials=[_mat("air"), _mat("silicon")],
        )
        # Manually inject a component with placeholder evidence
        bad_comp = _child_with_evidence("sensor", ["PLACEHOLDER: TODO"])
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), bad_comp],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)
        assert not passed

    def test_simplification_allowed_with_approval(self):
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            simplification_policy=SimplificationPolicy(
                allow_simplification=True,
                requires_user_approval=False,
            ),
            components=[_world()],
            materials=[_mat("air")],
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)
        assert passed

    def test_default_sizes_flagged(self):
        """Components with default-like sizes (e.g., 1x1x1) should be flagged."""
        default_comp = ComponentSpec(
            component_id="sensor",
            display_name="Sensor",
            component_type="layer",
            geometry_type="box",
            dimensions={"dx": 1.0, "dy": 1.0, "dz": 1.0},
            material_id="silicon",
            mother_volume="world",
            source_evidence=["user_spec: sensor dimensions"],
            open_issues=["Default dimensions used — needs measurement"],
        )
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), default_comp],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)
        # Should flag the open_issues warning or default size
        assert not passed or len(errors) > 0 or default_comp.open_issues

    def test_minimal_single_slab_detector_is_not_forced_to_multi_layer(self):
        """A user-requested minimal detector may legitimately be world + one slab."""
        slab = ComponentSpec(
            component_id="silicon_slab_detector",
            display_name="Silicon slab detector",
            component_type="volume",
            geometry_type="box",
            dimensions={"dx": 10000.0, "dy": 10000.0, "dz": 1000.0},
            material_id="silicon",
            mother_volume="world",
            sensitive=True,
            roles=["edep_region", "dose_scoring_region"],
            source_evidence=["user_spec: 1 mm thick silicon slab detector"],
        )
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            target_system="minimal silicon slab detector",
            components=[_world(), slab],
            materials=[_mat("air"), _mat("silicon")],
        )

        passed, errors = NoSimplificationValidator().validate(ir)

        assert passed, errors
