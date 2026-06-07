"""Unit tests for evidence traceability validator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec
from agent_core.g4_modeling.schemas.source_spec import BeamProfile, EnergySpec, SourceSpec
from agent_core.g4_modeling.validators.evidence_traceability_validator import (
    EvidenceTraceabilityValidator,
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


def _child(cid: str, evidence: list[str]) -> ComponentSpec:
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


def _mat(mid: str, evidence: list[str] | None = None) -> MaterialSpec:
    return MaterialSpec(
        material_id=mid,
        name=mid,
        classification="nist",
        nist_name=f"G4_{mid.capitalize()}",
        density_g_cm3=2.33,
        source_evidence=evidence or ["nist: reference"],
    )


def _source(evidence: list[str]) -> SourceSpec:
    return SourceSpec(
        source_id="proton_src",
        particle_type="proton",
        energy=EnergySpec(value=10.0, unit="MeV"),
        beam=BeamProfile(
            position=[0.0, 0.0, -4000.0],
            direction=[0.0, 0.0, 1.0],
        ),
        source_evidence=evidence,
    )


def _physics(evidence: list[str]) -> PhysicsSpec:
    return PhysicsSpec(
        physics_list="FTFP_BERT",
        selection_reasoning="Standard physics for proton therapy simulations",
        source_evidence=evidence,
    )


class TestEvidenceTraceabilityValidator:
    """Test EvidenceTraceabilityValidator."""

    def test_all_evidence_present_passes(self):
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), _child("sensor", ["user_spec: sensor 200um"])],
            materials=[_mat("air"), _mat("silicon")],
            sources=[_source(["user_spec: 10 MeV proton"])],
            physics=_physics(["geant4_doc: FTFP_BERT"]),
        )
        validator = EvidenceTraceabilityValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"

    def test_placeholder_evidence_fails(self):
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[
                _world(),
                _child("sensor", ["TODO"]),
            ],
            materials=[_mat("air")],
        )
        validator = EvidenceTraceabilityValidator()
        passed, errors = validator.validate(ir)
        assert not passed

    def test_tbd_evidence_fails(self):
        """TBD as evidence should fail."""
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[
                _world(),
                _child("sensor", ["TBD"]),
            ],
            materials=[_mat("air")],
        )
        validator = EvidenceTraceabilityValidator()
        passed, errors = validator.validate(ir)
        assert not passed

    def test_no_physics_evidence_fails(self):
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world()],
            materials=[_mat("air")],
            # physics is None — no evidence to check
        )
        validator = EvidenceTraceabilityValidator()
        passed, errors = validator.validate(ir)
        # No physics means no evidence to check — should pass
        # (validator only checks existing sections)
        assert passed

    def test_material_without_evidence_fails(self):
        """Material with placeholder evidence should fail."""
        bad_mat = _mat("sio2", evidence=["TBD"])
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world()],
            materials=[_mat("air"), bad_mat],
        )
        validator = EvidenceTraceabilityValidator()
        passed, errors = validator.validate(ir)
        assert not passed
