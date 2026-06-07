"""Tests for G4-B No Unapproved Simplification Gate — hard checks.

Validates that the gate can detect:
1. Missing complex components (housing, pcb, oxide, electrodes)
2. Multi-layer merge (single silicon box instead of stack)
3. Oversimplified model claiming to be complex
"""

from __future__ import annotations

from agent_core.g4_modeling.schemas.component_spec import ComponentSpec
from agent_core.g4_modeling.schemas.g4_model_ir import (
    ConstructionLedger,
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
        material_id="G4_AIR",
        source_evidence=["standard:world_volume"],
    )


def _component(
    cid: str,
    display_name: str,
    geometry_type: str = "box",
    dimensions: dict | None = None,
    material_id: str = "G4_Si",
    mother_volume: str = "world",
    comp_type: str = "volume",
    roles: list[str] | None = None,
) -> ComponentSpec:
    return ComponentSpec(
        component_id=cid,
        display_name=display_name,
        component_type=comp_type,
        geometry_type=geometry_type,
        dimensions=dimensions or {"dx": 50.0, "dy": 50.0, "dz": 5.0},
        material_id=material_id,
        mother_volume=mother_volume,
        roles=roles or [],
        source_evidence=["user_specification"],
    )


def _mat(mid: str, name: str, density: float = 2.33) -> MaterialSpec:
    return MaterialSpec(
        material_id=mid,
        name=name,
        classification="nist",
        nist_name=name,
        density_g_cm3=density,
        source_evidence=["NIST"],
    )


def _basic_materials() -> list[MaterialSpec]:
    return [
        _mat("G4_AIR", "G4_AIR", 0.001214),
        _mat("G4_Si", "G4_Si", 2.329),
    ]


class TestNoSimplificationGateHard:
    """Hard tests for G4-B: must detect oversimplified models."""

    def test_oversimplified_model_detected(self) -> None:
        """A model with only world + silicon_detector but complex target_system must FAIL."""
        ir = G4ModelIR(
            model_ir_id="oversimplified",
            job_id="test",
            modeling_mode="realistic",
            target_system="Radiation-Hard Silicon Pixel Detector",
            simplification_policy=SimplificationPolicy(),
            components=[
                _world(),
                _component("silicon_detector", "Silicon Detector"),
            ],
            materials=_basic_materials(),
            ledger=ConstructionLedger(),
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)

        assert not passed, f"Oversimplified model should fail, but passed. Errors: {errors}"
        error_text = " ".join(errors).lower()
        # Should detect missing housing, pcb, oxide, electrodes, sensitive
        assert "housing" in error_text or "complex" in error_text or "layer merge" in error_text

    def test_complex_model_with_all_components_passes(self) -> None:
        """A model with all complex components should PASS."""
        ir = G4ModelIR(
            model_ir_id="complete_detector",
            job_id="test",
            modeling_mode="realistic",
            target_system="Radiation-Hard Silicon Pixel Detector",
            simplification_policy=SimplificationPolicy(),
            components=[
                _world(),
                _component("housing", "Aluminum Housing", material_id="G4_Al"),
                _component("pcb", "FR4 PCB Carrier", material_id="FR4"),
                _component("sensor_stack", "Sensor Stack", comp_type="assembly"),
                _component(
                    "top_electrode",
                    "Top Aluminum Electrode",
                    material_id="G4_Al",
                    mother_volume="sensor_stack",
                ),
                _component(
                    "oxide_layer",
                    "Gate Oxide SiO2",
                    material_id="SiO2",
                    dimensions={"dx": 50.0, "dy": 50.0, "dz": 0.001},
                    mother_volume="sensor_stack",
                ),
                _component("silicon_bulk", "Silicon Bulk", mother_volume="sensor_stack"),
                _component(
                    "sensitive_region",
                    "Sensitive Active Region",
                    mother_volume="silicon_bulk",
                    roles=["edep_region"],
                ),
                _component(
                    "bottom_electrode",
                    "Bottom Aluminum Electrode",
                    material_id="G4_Al",
                    mother_volume="sensor_stack",
                ),
            ],
            materials=[
                _mat("G4_AIR", "G4_AIR", 0.001214),
                _mat("G4_Al", "G4_Al", 2.699),
                _mat("G4_Si", "G4_Si", 2.329),
                _mat("FR4", "FR4_Epoxy", 1.85),
                _mat("SiO2", "SiO2", 2.2),
            ],
            ledger=ConstructionLedger(),
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Complete model should pass. Errors: {errors}"

    def test_missing_housing_detected(self) -> None:
        """Missing housing in a complex detector model must be detected."""
        ir = G4ModelIR(
            model_ir_id="no_housing",
            job_id="test",
            modeling_mode="realistic",
            target_system="Silicon Strip Sensor Detector Module",
            simplification_policy=SimplificationPolicy(),
            components=[
                _world(),
                _component("pcb", "PCB Board", material_id="FR4"),
                _component("sensor_stack", "Sensor Stack", comp_type="assembly"),
                _component(
                    "oxide_layer", "Gate Oxide", material_id="SiO2", mother_volume="sensor_stack"
                ),
                _component(
                    "top_electrode", "Top Metal", material_id="G4_Al", mother_volume="sensor_stack"
                ),
                _component(
                    "sensitive",
                    "Sensitive Region",
                    mother_volume="sensor_stack",
                    roles=["edep_region"],
                ),
                _component(
                    "bottom_electrode",
                    "Bottom Metal",
                    material_id="G4_Al",
                    mother_volume="sensor_stack",
                ),
            ],
            materials=_basic_materials(),
            ledger=ConstructionLedger(),
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)
        assert not passed, "Missing housing should be detected"
        error_text = " ".join(errors).lower()
        assert "housing" in error_text

    def test_two_component_merge_detected(self) -> None:
        """Only 2 non-world components for a complex detector = layer merge simplification."""
        ir = G4ModelIR(
            model_ir_id="merged_layers",
            job_id="test",
            modeling_mode="realistic",
            target_system="Pixel Detector Stack",
            simplification_policy=SimplificationPolicy(),
            components=[
                _world(),
                _component("housing", "Aluminum Housing", material_id="G4_Al"),
                _component("sensor", "Sensor", roles=["edep_region"]),
            ],
            materials=_basic_materials(),
            ledger=ConstructionLedger(),
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)
        # Should detect either missing components or layer merge
        assert not passed, f"Merged layers should be detected. Errors: {errors}"

    def test_simple_model_not_flagged(self) -> None:
        """A genuinely simple model (no complex keywords) should pass."""
        ir = G4ModelIR(
            model_ir_id="simple",
            job_id="test",
            modeling_mode="realistic",
            target_system="Simple Water Phantom",
            simplification_policy=SimplificationPolicy(),
            components=[
                _world(),
                _component("phantom", "Water Phantom", material_id="G4_WATER"),
            ],
            materials=[
                _mat("G4_AIR", "G4_AIR", 0.001214),
                _mat("G4_WATER", "G4_WATER", 1.0),
            ],
            ledger=ConstructionLedger(),
        )
        validator = NoSimplificationValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Simple model should pass. Errors: {errors}"
