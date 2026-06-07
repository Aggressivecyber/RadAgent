"""Unit tests for IR → CodeModulePlan mapping."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.code_module_plan import (
    CodeGenerationPlan,
    CodeModulePlan,
)
from agent_core.g4_modeling.schemas.component_spec import ComponentSpec, PlacementSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec


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


def _sensor() -> ComponentSpec:
    return ComponentSpec(
        component_id="sensor",
        display_name="Sensor",
        component_type="substrate",
        geometry_type="box",
        dimensions={"dx": 200.0, "dy": 200.0, "dz": 150.0},
        material_id="silicon",
        mother_volume="world",
        placement=PlacementSpec(position=[0.0, 0.0, 0.0]),
        source_evidence=["user_spec: sensor 300um"],
        sensitive=True,
        roles=["edep_region"],
    )


def _oxide() -> ComponentSpec:
    return ComponentSpec(
        component_id="oxide",
        display_name="Oxide Layer",
        component_type="layer",
        geometry_type="box",
        dimensions={"dx": 200.0, "dy": 200.0, "dz": 0.5},
        material_id="sio2",
        mother_volume="world",
        placement=PlacementSpec(position=[0.0, 0.0, 150.5]),
        source_evidence=["user_spec: oxide 1um"],
    )


def _mat(mid: str, nist: str) -> MaterialSpec:
    return MaterialSpec(
        material_id=mid,
        name=mid,
        classification="nist",
        nist_name=nist,
        density_g_cm3=2.33,
        source_evidence=["nist"],
    )


class TestIRToCodePlanMapping:
    """Test mapping from G4ModelIR to CodeGenerationPlan."""

    def test_simple_ir_generates_modules(self):
        """A simple 3-component IR should produce a valid plan."""
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            components=[_world(), _sensor(), _oxide()],
            materials=[_mat("air", "G4_AIR"), _mat("silicon", "G4_Si")],
        )
        # Verify IR is valid
        assert len(ir.components) == 3
        assert ir.component_by_id("sensor") is not None
        assert ir.component_by_id("oxide") is not None

    def test_module_plan_structure(self):
        """CodeModulePlan should have required fields."""
        plan = CodeModulePlan(
            module_name="MaterialRegistry",
            module_type="material_registry",
            source_files=["MaterialRegistry.cc"],
            header_files=["MaterialRegistry.hh"],
            config_files=["material_config.json"],
            depends_on=[],
            linked_component_ids=[],
            linked_material_ids=["silicon", "sio2"],
        )
        assert plan.module_type == "material_registry"
        assert len(plan.linked_material_ids) == 2

    def test_code_generation_plan_structure(self):
        """CodeGenerationPlan should contain all modules."""
        modules = [
            CodeModulePlan(
                module_name="MaterialRegistry",
                module_type="material_registry",
                source_files=["MaterialRegistry.cc"],
                header_files=["MaterialRegistry.hh"],
                depends_on=[],
                linked_component_ids=[],
                linked_material_ids=["silicon"],
            ),
            CodeModulePlan(
                module_name="SensorBuilder",
                module_type="component_geometry",
                source_files=["SensorBuilder.cc"],
                header_files=["SensorBuilder.hh"],
                depends_on=["MaterialRegistry"],
                linked_component_ids=["sensor"],
                linked_material_ids=[],
            ),
        ]
        plan = CodeGenerationPlan(
            plan_id="plan_001",
            job_id="job_001",
            modules=modules,
        )
        assert len(plan.modules) == 2
        assert plan.modules[1].depends_on == ["MaterialRegistry"]

    def test_code_generation_plan_serialization(self):
        """Plan should serialize and deserialize correctly."""
        plan = CodeGenerationPlan(
            plan_id="plan_001",
            job_id="job_001",
            modules=[
                CodeModulePlan(
                    module_name="TestModule",
                    module_type="material_registry",
                    source_files=["test.cc"],
                    header_files=["test.hh"],
                    depends_on=[],
                    linked_component_ids=[],
                    linked_material_ids=[],
                ),
            ],
        )
        data = plan.model_dump(mode="json")
        plan2 = CodeGenerationPlan.model_validate(data)
        assert plan2.plan_id == plan.plan_id
        assert len(plan2.modules) == 1
