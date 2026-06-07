"""Unit tests for G4ModelIR schema and sub-schemas."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec, PlacementSpec
from agent_core.g4_modeling.schemas.construction_ledger import (
    ConstructionLedger,
    ConstructionLedgerEntry,
)
from agent_core.g4_modeling.schemas.g4_model_ir import (
    CoordinateSystem,
    EvidencePack,
    G4ModelIR,
    GlobalUnits,
    SimplificationPolicy,
    validate_g4_model_ir,
)
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.schemas.physics_spec import PhysicsSpec, validate_physics_spec
from agent_core.g4_modeling.schemas.source_spec import SourceSpec


def _make_world() -> ComponentSpec:
    return ComponentSpec(
        component_id="world",
        display_name="World",
        component_type="world",
        geometry_type="box",
        dimensions={"dx": 5000.0, "dy": 5000.0, "dz": 5000.0},
        material_id="air",
        source_evidence=["user_spec: world 10mm"],
    )


def _make_silicon() -> ComponentSpec:
    return ComponentSpec(
        component_id="silicon_bulk",
        display_name="Silicon Bulk",
        component_type="substrate",
        geometry_type="box",
        dimensions={"dx": 500.0, "dy": 500.0, "dz": 150.0},
        material_id="silicon",
        mother_volume="world",
        placement=PlacementSpec(position=[0.0, 0.0, 0.0]),
        source_evidence=["user_spec: silicon 300um"],
        sensitive=True,
        roles=["edep_region"],
    )


def _make_material() -> MaterialSpec:
    return MaterialSpec(
        material_id="silicon",
        name="Silicon",
        classification="nist",
        nist_name="G4_Si",
        density_g_cm3=2.33,
        source_evidence=["nist: G4_Si"],
    )


def _make_source() -> SourceSpec:
    from agent_core.g4_modeling.schemas.source_spec import BeamProfile, EnergySpec

    return SourceSpec(
        source_id="proton_source",
        particle_type="proton",
        energy=EnergySpec(value=10.0, unit="MeV"),
        beam=BeamProfile(
            position=[0.0, 0.0, -4000.0],
            direction=[0.0, 0.0, 1.0],
        ),
        source_evidence=["user_spec: 10 MeV proton"],
    )


def _make_physics() -> PhysicsSpec:
    return PhysicsSpec(
        physics_list="FTFP_BERT",
        selection_reasoning="Standard EM + Bertini hadronics for proton therapy range",
        source_evidence=["geant4_doc: FTFP_BERT reference physics list"],
    )


def _make_minimal_ir() -> G4ModelIR:
    return G4ModelIR(
        model_ir_id="test_ir_001",
        job_id="job_001",
        components=[_make_world(), _make_silicon()],
        materials=[_make_material()],
        sources=[_make_source()],
        physics=_make_physics(),
    )


class TestG4ModelIRConstruction:
    """Test G4ModelIR creation and basic operations."""

    def test_minimal_ir_creation(self):
        ir = _make_minimal_ir()
        assert ir.model_ir_id == "test_ir_001"
        assert ir.job_id == "job_001"
        assert len(ir.components) == 2
        assert len(ir.materials) == 1
        assert ir.physics is not None

    def test_component_by_id(self):
        ir = _make_minimal_ir()
        c = ir.component_by_id("silicon_bulk")
        assert c is not None
        assert c.component_type == "substrate"

    def test_component_by_id_missing(self):
        ir = _make_minimal_ir()
        assert ir.component_by_id("nonexistent") is None

    def test_material_by_id(self):
        ir = _make_minimal_ir()
        m = ir.material_by_id("silicon")
        assert m is not None
        assert m.nist_name == "G4_Si"

    def test_children_of(self):
        ir = _make_minimal_ir()
        children = ir.children_of("world")
        assert len(children) == 1
        assert children[0].component_id == "silicon_bulk"

    def test_serialization_roundtrip(self):
        ir = _make_minimal_ir()
        data = ir.model_dump(mode="json")
        ir2 = G4ModelIR.model_validate(data)
        assert ir2.model_ir_id == ir.model_ir_id
        assert len(ir2.components) == len(ir.components)


class TestG4ModelIRValidation:
    """Test G4ModelIR validation rules."""

    def test_missing_model_ir_id_fails(self):
        ir, errors = validate_g4_model_ir({
            "job_id": "job_001",
        })
        assert ir is None
        assert len(errors) > 0

    def test_no_world_volume_fails(self):
        data = {
            "model_ir_id": "test_ir",
            "job_id": "job_001",
            "components": [
                {
                    "component_id": "sensor",
                    "display_name": "Sensor",
                    "component_type": "substrate",
                    "geometry_type": "box",
                    "dimensions": {"dx": 100.0, "dy": 100.0, "dz": 50.0},
                    "material_id": "silicon",
                    "mother_volume": "world",
                    "source_evidence": ["user_spec"],
                },
            ],
        }
        ir, errors = validate_g4_model_ir(data)
        assert ir is None or len(errors) > 0

    def test_two_world_volumes_fails(self):
        w1 = _make_world().model_dump()
        w2 = _make_world()
        w2_dict = w2.model_dump()
        w2_dict["component_id"] = "world_2"
        data = {
            "model_ir_id": "test_ir",
            "job_id": "job_001",
            "components": [w1, w2_dict],
        }
        ir, errors = validate_g4_model_ir(data)
        assert ir is None or len(errors) > 0


class TestSubSchemas:
    """Test sub-schema construction."""

    def test_coordinate_system_defaults(self):
        cs = CoordinateSystem()
        assert cs.system == "cartesian"
        assert cs.unit == "um"

    def test_global_units_defaults(self):
        gu = GlobalUnits()
        assert gu.length == "um"
        assert gu.energy == "MeV"

    def test_simplification_policy_defaults(self):
        sp = SimplificationPolicy()
        assert sp.allow_simplification is False
        assert sp.requires_user_approval is True

    def test_evidence_pack_creation(self):
        ep = EvidencePack(
            evidence_decision="allow_rag",
            geometry=[{"doc_id": 42, "snippet": "detector geometry"}],
        )
        assert ep.evidence_decision == "allow_rag"
        assert len(ep.geometry) == 1

    def test_construction_ledger(self):
        entry = ConstructionLedgerEntry(
            node_name="geometry_decomposition_node",
            action="create",
            target_id="silicon_bulk",
            description="Added silicon substrate",
        )
        ledger = ConstructionLedger(steps=[entry])
        assert len(ledger.steps) == 1

    def test_construction_ledger_add_entry(self):
        ledger = ConstructionLedger()
        ledger.add_entry(
            node_name="test_node",
            action="create",
            target_id="test_target",
            description="Test entry",
        )
        assert len(ledger.steps) == 1
        assert ledger.steps[0].node_name == "test_node"


class TestPhysicsSpec:
    """Test PhysicsSpec validation."""

    def test_valid_physics_spec(self):
        spec, errors = validate_physics_spec({
            "physics_list": "FTFP_BERT",
            "selection_reasoning": "Standard physics for proton simulations",
            "source_evidence": ["doc:1"],
        })
        assert spec is not None
        assert not errors

    def test_short_reasoning_fails(self):
        spec, errors = validate_physics_spec({
            "physics_list": "FTFP_BERT",
            "selection_reasoning": "short",
            "source_evidence": ["doc:1"],
        })
        assert spec is None
        assert any("reasoning" in e.lower() for e in errors)

    def test_empty_evidence_fails(self):
        spec, errors = validate_physics_spec({
            "physics_list": "FTFP_BERT",
            "selection_reasoning": "Valid reasoning for proton therapy",
            "source_evidence": [],
        })
        assert spec is None or len(errors) > 0
