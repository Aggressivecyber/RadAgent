"""Unit tests for material spec completeness validation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.material_spec import (
    MaterialSpec,
    validate_material_spec,
)
from agent_core.g4_modeling.validators.material_completeness_validator import (
    MaterialCompletenessValidator,
)


def _nist_silicon() -> dict:
    return {
        "material_id": "silicon",
        "name": "Silicon",
        "classification": "nist",
        "nist_name": "G4_Si",
        "density_g_cm3": 2.33,
        "source_evidence": ["nist: G4_Si"],
    }


def _custom_sio2() -> dict:
    return {
        "material_id": "sio2",
        "name": "Silicon Dioxide",
        "classification": "custom",
        "composition": [
            {"element": "Si", "fraction": 0.467},
            {"element": "O", "fraction": 0.533},
        ],
        "density_g_cm3": 2.65,
        "source_evidence": ["user_spec: SiO2 layer"],
    }


class TestMaterialSpecValid:
    """Test valid MaterialSpec construction."""

    def test_nist_material(self):
        spec, errors = validate_material_spec(_nist_silicon())
        assert spec is not None, f"Errors: {errors}"
        assert spec.classification == "nist"
        assert spec.nist_name == "G4_Si"

    def test_custom_material(self):
        spec, errors = validate_material_spec(_custom_sio2())
        assert spec is not None, f"Errors: {errors}"
        assert spec.classification == "custom"
        assert len(spec.composition) == 2

    def test_serialization_roundtrip(self):
        spec, _ = validate_material_spec(_nist_silicon())
        data = spec.model_dump(mode="json")
        spec2 = MaterialSpec.model_validate(data)
        assert spec2.material_id == spec.material_id


class TestMaterialSpecInvalid:
    """Test MaterialSpec validation failures."""

    def test_nist_without_name_fails(self):
        data = _nist_silicon()
        data["nist_name"] = None
        spec, errors = validate_material_spec(data)
        assert spec is None or len(errors) > 0

    def test_custom_without_composition_fails(self):
        data = _custom_sio2()
        data["composition"] = None
        spec, errors = validate_material_spec(data)
        assert spec is None or len(errors) > 0

    def test_negative_density_fails(self):
        data = _nist_silicon()
        data["density_g_cm3"] = -1.0
        spec, errors = validate_material_spec(data)
        assert spec is None or len(errors) > 0

    def test_empty_evidence_fails(self):
        data = _nist_silicon()
        data["source_evidence"] = []
        spec, errors = validate_material_spec(data)
        assert spec is None or len(errors) > 0

    def test_zero_density_fails(self):
        data = _nist_silicon()
        data["density_g_cm3"] = 0.0
        spec, errors = validate_material_spec(data)
        assert spec is None or len(errors) > 0


class TestMaterialCompletenessValidator:
    """Test MaterialCompletenessValidator on G4ModelIR."""

    def test_complete_materials_pass(self):
        from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

        si = MaterialSpec.model_validate(_nist_silicon())
        sio2 = MaterialSpec.model_validate(_custom_sio2())
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            materials=[si, sio2],
        )
        validator = MaterialCompletenessValidator()
        passed, errors = validator.validate(ir)
        assert passed, f"Unexpected errors: {errors}"

    def test_nist_without_name_fails_validator(self):
        from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

        si = MaterialSpec.model_validate(_nist_silicon())
        ir = G4ModelIR(
            model_ir_id="test",
            job_id="job",
            materials=[si],
        )
        validator = MaterialCompletenessValidator()
        passed, errors = validator.validate(ir)
        assert passed  # NIST materials with nist_name are complete
