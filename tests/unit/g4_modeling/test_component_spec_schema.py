"""Unit tests for ComponentSpec schema validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from agent_core.g4_modeling.schemas.component_spec import (
    PlacementSpec,
    validate_component_spec,
)


def _valid_world_data() -> dict:
    return {
        "component_id": "world",
        "display_name": "World Volume",
        "component_type": "world",
        "geometry_type": "box",
        "dimensions": {"dx": 5000.0, "dy": 5000.0, "dz": 5000.0},
        "material_id": "air",
        "source_evidence": ["user_spec: world 10mm"],
    }


def _valid_child_data() -> dict:
    return {
        "component_id": "silicon_bulk",
        "display_name": "Silicon Bulk",
        "component_type": "substrate",
        "geometry_type": "box",
        "dimensions": {"dx": 500.0, "dy": 500.0, "dz": 150.0},
        "material_id": "silicon",
        "mother_volume": "world",
        "placement": {"position": [0.0, 0.0, 100.0], "rotation": [0.0, 0.0, 0.0]},
        "source_evidence": ["user_spec: silicon 300um"],
        "sensitive": True,
        "roles": ["edep_region"],
    }


class TestComponentSpecValid:
    """Test valid ComponentSpec construction."""

    def test_world_volume(self):
        spec, errors = validate_component_spec(_valid_world_data())
        assert spec is not None, f"Errors: {errors}"
        assert spec.component_id == "world"
        assert spec.mother_volume is None

    def test_child_volume(self):
        spec, errors = validate_component_spec(_valid_child_data())
        assert spec is not None, f"Errors: {errors}"
        assert spec.mother_volume == "world"
        assert spec.sensitive is True
        assert "edep_region" in spec.roles

    def test_all_component_types(self):
        for ctype in (
            "world",
            "assembly",
            "layer",
            "volume",
            "shielding",
            "electrode",
            "substrate",
        ):
            data = _valid_world_data()
            data["component_id"] = f"test_{ctype}"
            data["component_type"] = ctype
            if ctype != "world":
                data["mother_volume"] = "world"
            spec, errors = validate_component_spec(data)
            assert spec is not None, f"Failed for {ctype}: {errors}"

    def test_all_geometry_types(self):
        for gtype in ("box", "sphere", "cylinder", "tubs", "cons", "polycone", "trapezoid"):
            data = _valid_world_data()
            data["geometry_type"] = gtype
            spec, errors = validate_component_spec(data)
            assert spec is not None, f"Failed for {gtype}: {errors}"


class TestComponentSpecInvalid:
    """Test ComponentSpec validation failures."""

    def test_empty_component_id(self):
        data = _valid_world_data()
        data["component_id"] = ""
        spec, errors = validate_component_spec(data)
        assert spec is None or len(errors) > 0

    def test_missing_dimensions(self):
        data = _valid_world_data()
        del data["dimensions"]
        spec, errors = validate_component_spec(data)
        assert spec is None

    def test_missing_material_id(self):
        data = _valid_world_data()
        del data["material_id"]
        spec, errors = validate_component_spec(data)
        assert spec is None

    def test_empty_source_evidence(self):
        data = _valid_world_data()
        data["source_evidence"] = []
        spec, errors = validate_component_spec(data)
        assert spec is None or len(errors) > 0

    def test_non_world_with_no_mother_fails(self):
        """Non-world component without mother_volume should fail."""
        data = _valid_child_data()
        # Remove mother_volume but keep component_type as 'substrate'
        data["mother_volume"] = None
        spec, errors = validate_component_spec(data)
        assert spec is None or len(errors) > 0

    def test_invalid_component_type(self):
        data = _valid_world_data()
        data["component_type"] = "unknown_type"
        spec, errors = validate_component_spec(data)
        assert spec is None

    def test_invalid_geometry_type(self):
        data = _valid_world_data()
        data["geometry_type"] = "torus"
        spec, errors = validate_component_spec(data)
        assert spec is None


class TestPlacementSpec:
    """Test PlacementSpec validation."""

    def test_valid_placement(self):
        p = PlacementSpec(position=[1.0, 2.0, 3.0])
        assert p.position == [1.0, 2.0, 3.0]
        assert p.rotation == [0.0, 0.0, 0.0]

    def test_position_must_have_3_elements(self):
        with pytest.raises(Exception):
            PlacementSpec(position=[1.0, 2.0])

    def test_rotation_must_have_3_elements(self):
        with pytest.raises(Exception):
            PlacementSpec(position=[1.0, 2.0, 3.0], rotation=[1.0])
