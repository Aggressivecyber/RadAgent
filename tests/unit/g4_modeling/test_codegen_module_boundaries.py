"""Unit tests for codegen module boundary validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.code_module_plan import (
    CodeGenerationPlan,
    CodeModulePlan,
)
from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.schemas.material_spec import MaterialSpec
from agent_core.g4_modeling.validators.code_module_boundary_validator import (
    CodeModuleBoundaryValidator,
)


def _valid_module(name: str, module_type: str, files: list[str]) -> CodeModulePlan:
    return CodeModulePlan(
        module_name=name,
        module_type=module_type,
        source_files=[f for f in files if f.endswith(".cc")],
        header_files=[f for f in files if f.endswith(".hh")],
        config_files=[f for f in files if f.endswith(".json") or f.endswith(".mac")],
        depends_on=[],
        linked_component_ids=[],
        linked_material_ids=[],
    )


def _valid_plan() -> CodeGenerationPlan:
    return CodeGenerationPlan(
        plan_id="plan_001",
        job_id="job_001",
        modules=[
            _valid_module(
                "MaterialRegistry",
                "material_registry",
                ["MaterialRegistry.cc", "MaterialRegistry.hh", "material_config.json"],
            ),
            _valid_module(
                "SiliconBuilder",
                "component_geometry",
                ["SiliconBuilder.cc", "SiliconBuilder.hh"],
            ),
            _valid_module(
                "PlacementManager",
                "placement",
                ["PlacementManager.cc", "PlacementManager.hh"],
            ),
        ],
    )


class TestCodeModuleBoundaryValidator:
    """Test CodeModuleBoundaryValidator."""

    def _make_ir(self) -> G4ModelIR:
        return G4ModelIR(
            model_ir_id="test",
            job_id="job_001",
            components=[
                ComponentSpec(
                    component_id="world",
                    display_name="World",
                    component_type="world",
                    geometry_type="box",
                    dimensions={"dx": 5000.0, "dy": 5000.0, "dz": 5000.0},
                    material_id="air",
                    source_evidence=["user_spec"],
                ),
                ComponentSpec(
                    component_id="sensor",
                    display_name="Sensor",
                    component_type="substrate",
                    geometry_type="box",
                    dimensions={"dx": 100.0, "dy": 100.0, "dz": 10.0},
                    material_id="silicon",
                    mother_volume="world",
                    source_evidence=["user_spec"],
                ),
            ],
            materials=[
                MaterialSpec(
                    material_id="air",
                    name="Air",
                    classification="nist",
                    nist_name="G4_AIR",
                    density_g_cm3=0.001225,
                    source_evidence=["nist"],
                ),
                MaterialSpec(
                    material_id="silicon",
                    name="Silicon",
                    classification="nist",
                    nist_name="G4_Si",
                    density_g_cm3=2.33,
                    source_evidence=["nist"],
                ),
            ],
        )

    def test_valid_plan_passes(self):
        plan = _valid_plan()
        ir = self._make_ir()
        validator = CodeModuleBoundaryValidator()
        passed, errors = validator.validate(plan, ir)
        assert passed, f"Errors: {errors}"

    def test_material_module_with_undefined_material_fails(self):
        """Module referencing undefined material should fail."""
        bad_module = CodeModulePlan(
            module_name="MaterialRegistry",
            module_type="material_registry",
            source_files=["MaterialRegistry.cc"],
            header_files=["MaterialRegistry.hh"],
            depends_on=[],
            linked_component_ids=[],
            linked_material_ids=["nonexistent_mat"],
        )
        plan = CodeGenerationPlan(
            plan_id="plan_001",
            job_id="job_001",
            modules=[bad_module],
        )
        ir = self._make_ir()
        validator = CodeModuleBoundaryValidator()
        passed, errors = validator.validate(plan, ir)
        assert not passed
        assert any("nonexistent_mat" in e for e in errors)

    def test_single_module_plan_passes(self):
        """Plan with one valid module passes."""
        plan = CodeGenerationPlan(
            plan_id="plan_001",
            job_id="job_001",
            modules=[
                _valid_module(
                    "MaterialRegistry",
                    "material_registry",
                    ["MaterialRegistry.cc", "MaterialRegistry.hh"],
                ),
            ],
        )
        ir = self._make_ir()
        validator = CodeModuleBoundaryValidator()
        passed, errors = validator.validate(plan, ir)
        assert passed, f"Errors: {errors}"

    def test_multiple_valid_modules_passes(self):
        modules = [
            _valid_module(f"Builder{i}", "component_geometry", [f"Builder{i}.cc", f"Builder{i}.hh"])
            for i in range(5)
        ]
        plan = CodeGenerationPlan(
            plan_id="plan_001",
            job_id="job_001",
            modules=modules,
        )
        ir = self._make_ir()
        validator = CodeModuleBoundaryValidator()
        passed, errors = validator.validate(plan, ir)
        assert passed, f"Errors: {errors}"
