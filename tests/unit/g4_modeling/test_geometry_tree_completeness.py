"""Unit tests for geometry tree completeness — no orphans, single root, no cycles."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.validators.geometry_interface_validator import (
    GeometryInterfaceValidator,
)
from agent_core.g4_modeling.validators.model_completeness_validator import (
    ModelCompletenessValidator,
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


def _child(cid: str, mother: str = "world") -> ComponentSpec:
    return ComponentSpec(
        component_id=cid,
        display_name=cid,
        component_type="layer",
        geometry_type="box",
        dimensions={"dx": 100.0, "dy": 100.0, "dz": 10.0},
        material_id="silicon",
        mother_volume=mother,
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


class TestGeometryTreeCompleteness:
    """Test geometry tree integrity via validators."""

    def test_valid_tree_passes(self):
        """Valid tree with all required sections passes completeness."""
        from agent_core.g4_modeling.schemas.geometry_interface_spec import GeometryInterfaceSpec
        from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec
        from agent_core.g4_modeling.schemas.scoring_spec import ScoringSpec
        from agent_core.g4_modeling.schemas.sensitive_detector_spec import (
            HitFieldSpec,
            SensitiveDetectorSpec,
        )
        from agent_core.g4_modeling.schemas.source_spec import BeamProfile, EnergySpec, SourceSpec

        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), _child("sensor")],
            materials=[_mat("air"), _mat("silicon")],
            interfaces=[
                GeometryInterfaceSpec(
                    interface_id="world_sensor",
                    component_a="world",
                    component_b="sensor",
                    relationship="contains",
                ),
            ],
            sources=[
                SourceSpec(
                    source_id="proton_src",
                    particle_type="proton",
                    energy=EnergySpec(value=10.0),
                    beam=BeamProfile(position=[0.0, 0.0, -4000.0], direction=[0.0, 0.0, 1.0]),
                    source_evidence=["user_spec"],
                ),
            ],
            physics=PhysicsSpec(
                physics_list="FTFP_BERT",
                selection_reasoning="Standard physics for proton therapy",
                source_evidence=["doc"],
            ),
            scoring=[
                ScoringSpec(
                    scoring_id="edep_score",
                    scoring_type="region",
                    quantities=["edep_MeV"],
                    source_evidence=["user_spec"],
                ),
            ],
            sensitive_detectors=[
                SensitiveDetectorSpec(
                    sd_id="sensor_sd",
                    name="SensorSD",
                    linked_component_ids=["sensor"],
                    hit_fields=[HitFieldSpec(name="edep_MeV")],
                ),
            ],
        )
        validator = ModelCompletenessValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"

    def test_no_components_fails_completeness(self):
        """Empty components list fails completeness check."""
        ir = G4ModelIR(model_ir_id="test", job_id="job")
        validator = ModelCompletenessValidator()
        passed, errors = validator.validate(ir)
        assert not passed
        assert any("No components" in e for e in errors)

    def test_box_components_require_complete_dimensions(self):
        """Box geometry must carry dx/dy/dz before code generation."""
        from agent_core.g4_modeling.schemas.geometry_interface_spec import GeometryInterfaceSpec
        from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec
        from agent_core.g4_modeling.schemas.scoring_spec import ScoringSpec
        from agent_core.g4_modeling.schemas.source_spec import BeamProfile, EnergySpec, SourceSpec

        incomplete_sensor = _child("sensor")
        incomplete_sensor.dimensions = {"dz": 10.0}
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), incomplete_sensor],
            materials=[_mat("air"), _mat("silicon")],
            interfaces=[
                GeometryInterfaceSpec(
                    interface_id="world_sensor",
                    component_a="world",
                    component_b="sensor",
                    relationship="contains",
                ),
            ],
            sources=[
                SourceSpec(
                    source_id="electron_src",
                    particle_type="electron",
                    energy=EnergySpec(value=1.0),
                    beam=BeamProfile(position=[0.0, 0.0, -100.0], direction=[0.0, 0.0, 1.0]),
                    source_evidence=["user_spec"],
                )
            ],
            physics=PhysicsSpec(
                physics_list="FTFP_BERT",
                selection_reasoning="Standard physics for electron test",
                source_evidence=["doc"],
            ),
            scoring=[
                ScoringSpec(
                    scoring_id="edep_score",
                    scoring_type="region",
                    quantities=["edep_MeV"],
                    source_evidence=["user_spec"],
                )
            ],
        )

        validator = ModelCompletenessValidator()
        passed, errors = validator.validate(ir)

        assert not passed
        assert any("sensor" in error and "dx" in error and "dy" in error for error in errors)

    def test_orphan_component_detected(self):
        """Child referencing non-existent mother should be flagged."""
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), _child("sensor", mother="nonexistent")],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = GeometryInterfaceValidator()
        passed, errors = validator.validate(ir)
        assert not passed
        assert any("nonexistent" in e or "orphan" in e.lower() for e in errors)

    def test_single_root_required(self):
        """Multiple world volumes should fail."""
        w1 = _world()
        w2 = ComponentSpec(
            component_id="world2",
            display_name="World2",
            component_type="world",
            geometry_type="box",
            dimensions={"dx": 100.0, "dy": 100.0, "dz": 100.0},
            material_id="air",
            source_evidence=["user_spec"],
        )
        with pytest.raises(Exception):
            G4ModelIR(
                model_ir_id="test",
                job_id="job",
                components=[w1, w2],
                materials=[_mat("air")],
            )

    def test_deep_tree_passes(self):
        """Multi-level tree should pass."""
        housing = ComponentSpec(
            component_id="housing",
            display_name="Housing",
            component_type="assembly",
            geometry_type="box",
            dimensions={"dx": 1000.0, "dy": 1000.0, "dz": 1000.0},
            material_id="aluminum",
            mother_volume="world",
            source_evidence=["user_spec"],
        )
        pcb = ComponentSpec(
            component_id="pcb",
            display_name="PCB",
            component_type="substrate",
            geometry_type="box",
            dimensions={"dx": 500.0, "dy": 500.0, "dz": 50.0},
            material_id="fr4",
            mother_volume="housing",
            source_evidence=["user_spec"],
        )
        sensor = ComponentSpec(
            component_id="sensor",
            display_name="Sensor",
            component_type="layer",
            geometry_type="box",
            dimensions={"dx": 200.0, "dy": 200.0, "dz": 10.0},
            material_id="silicon",
            mother_volume="pcb",
            source_evidence=["user_spec"],
        )
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), housing, pcb, sensor],
            materials=[_mat("air"), _mat("aluminum"), _mat("fr4"), _mat("silicon")],
        )
        validator = GeometryInterfaceValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"
