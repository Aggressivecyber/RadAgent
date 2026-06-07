"""Unit tests for geometry interface validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.geometry_interface_spec import GeometryInterfaceSpec
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.validators.geometry_interface_validator import (
    GeometryInterfaceValidator,
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


def _layer(cid: str, mother: str = "world") -> ComponentSpec:
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


class TestGeometryInterfaceValidator:
    """Test GeometryInterfaceValidator."""

    def test_valid_hierarchy_passes(self):
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), _layer("sensor")],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = GeometryInterfaceValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"

    def test_orphan_component_fails(self):
        orphan = ComponentSpec(
            component_id="orphan",
            display_name="Orphan",
            component_type="layer",
            geometry_type="box",
            dimensions={"dx": 10.0, "dy": 10.0, "dz": 10.0},
            material_id="silicon",
            mother_volume="nonexistent_parent",
            source_evidence=["user_spec"],
        )
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), orphan],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = GeometryInterfaceValidator()
        passed, errors = validator.validate(ir)
        assert not passed
        assert any("nonexistent_parent" in e or "orphan" in e.lower() for e in errors)

    def test_explicit_interfaces_pass(self):
        iface = GeometryInterfaceSpec(
            interface_id="world_sensor",
            component_a="world",
            component_b="sensor",
            relationship="contains",
        )
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), _layer("sensor")],
            interfaces=[iface],
            materials=[_mat("air"), _mat("silicon")],
        )
        validator = GeometryInterfaceValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Errors: {errors}"

    def test_invalid_interface_reference_fails(self):
        """Interface referencing non-existent components should fail."""
        iface = GeometryInterfaceSpec(
            interface_id="bad_iface",
            component_a="world",
            component_b="nonexistent",
            relationship="contains",
        )
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world()],
            interfaces=[iface],
            materials=[_mat("air")],
        )
        validator = GeometryInterfaceValidator()
        passed, errors = validator.validate(ir)
        assert not passed
        assert any("nonexistent" in e for e in errors)
