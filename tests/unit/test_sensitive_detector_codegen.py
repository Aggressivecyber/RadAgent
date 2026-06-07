"""Tests for sensitive_detector_codegen — contract and static C++ quality.

Verifies:
  - Empty sensitive_detectors → empty modules
  - Produces Hit.hh/.cc + SensitiveDetectorManager.hh/.cc
  - Concrete SD class (not abstract G4VSensitiveDetector)
  - linked_component_ids used for volume search
  - AttachAll calls all Attach methods
  - ProcessHits fills standard fields
  - C++ static quality: guards, includes, no bare G4int
"""

from __future__ import annotations

import re
from typing import Any


def _model_ir_with_sd() -> dict[str, Any]:
    """Return a model IR with sensitive detector."""
    return {
        "model_ir_id": "test_sd_codegen",
        "job_id": "test_sd_codegen",
        "modeling_mode": "realistic",
        "target_system": "Test Detector",
        "simplification_policy": {
            "allow_simplification": False,
            "requires_user_approval": True,
            "approved_simplifications": [],
        },
        "components": [
            {
                "component_id": "world",
                "display_name": "World",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 5000, "dy": 5000, "dz": 5000},
                "material_id": "G4_AIR",
                "source_evidence": ["standard"],
            },
            {
                "component_id": "sensor",
                "display_name": "Sensor",
                "component_type": "layer",
                "geometry_type": "box",
                "dimensions": {"dx": 100, "dy": 100, "dz": 10},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "source_evidence": ["user_spec"],
            },
        ],
        "materials": [
            {
                "material_id": "G4_AIR",
                "name": "G4_AIR",
                "classification": "nist",
                "nist_name": "G4_AIR",
                "density_g_cm3": 0.001214,
                "source_evidence": ["NIST"],
            },
            {
                "material_id": "G4_Si",
                "name": "G4_Si",
                "classification": "nist",
                "nist_name": "G4_Si",
                "density_g_cm3": 2.33,
                "source_evidence": ["NIST"],
            },
        ],
        "sources": [
            {
                "source_id": "proton",
                "particle_type": "proton",
                "energy": {"value": 10.0, "unit": "MeV"},
                "beam": {"position": [0, 0, 2500], "direction": [0, 0, -1]},
                "source_evidence": ["user_spec"],
            },
        ],
        "physics": {
            "physics_list": "QGSP_BIC",
            "selection_reasoning": "Standard EM for proton simulation",
            "source_evidence": ["geant4_guide"],
        },
        "scoring": [],
        "sensitive_detectors": [
            {
                "sd_id": "sensor_sd",
                "name": "SensorSD",
                "linked_component_ids": ["sensor"],
                "collection_name": "SensorHits",
                "hit_fields": [
                    {"name": "edep_MeV", "dtype": "double"},
                    {"name": "position_x", "dtype": "double"},
                ],
            },
        ],
        "ledger": {"entries": [], "version": "1.0"},
    }


async def _get_generated_code() -> dict[str, str]:
    """Run codegen and return {filename: content}."""
    from agent_core.g4_modeling.codegen.sensitive_detector_codegen import (
        sensitive_detector_codegen,
    )

    state = {"g4_model_ir": _model_ir_with_sd()}
    result = await sensitive_detector_codegen(state)
    return result["code_modules"][0]["generated_content"]


class TestSDContract:
    """Verify codegen output structure and content."""

    async def test_produces_all_files(self) -> None:
        code = await _get_generated_code()
        assert "SensitiveDetectorManager::Hit.hh" in code
        assert "SensitiveDetectorManager::Hit.cc" in code
        assert "SensitiveDetectorManager::SensitiveDetectorManager.hh" in code
        assert "SensitiveDetectorManager::SensitiveDetectorManager.cc" in code

    async def test_empty_sd_returns_empty(self) -> None:
        from agent_core.g4_modeling.codegen.sensitive_detector_codegen import (
            sensitive_detector_codegen,
        )

        model_ir = _model_ir_with_sd()
        model_ir["sensitive_detectors"] = []
        result = await sensitive_detector_codegen({"g4_model_ir": model_ir})
        assert result.get("code_modules", []) == []

    async def test_linked_component_ids_populated(self) -> None:
        from agent_core.g4_modeling.codegen.sensitive_detector_codegen import (
            sensitive_detector_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_sd()}
        result = await sensitive_detector_codegen(state)
        mod = result["code_modules"][0]
        assert "sensor" in mod["linked_component_ids"]

    async def test_concrete_sd_class_not_abstract(self) -> None:
        """Must create a concrete SD class, not new G4VSensitiveDetector."""
        code = await _get_generated_code()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]

        # Must NOT directly instantiate abstract G4VSensitiveDetector
        lines = source.splitlines()
        for line in lines:
            stripped = line.strip()
            if "new G4VSensitiveDetector" in stripped and "class" not in stripped:
                # Only allowed inside a concrete class definition
                if "public G4VSensitiveDetector" not in stripped:
                    raise AssertionError(
                        f"Direct abstract instantiation: {stripped}"
                    )

        # Must have a concrete class inheriting from G4VSensitiveDetector
        assert "public G4VSensitiveDetector" in source
        assert "ProcessHits" in source

    async def test_attach_searches_component_volume(self) -> None:
        """Attach method must search for the component's logical volume."""
        code = await _get_generated_code()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]

        # Must reference component_id in volume search
        assert "sensor_logical" in source

    async def test_attach_all_calls_per_sd(self) -> None:
        """AttachAll must call each per-SD attach method."""
        code = await _get_generated_code()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]

        assert "AttachSensorSd(worldLogical)" in source

    async def test_process_hits_fills_standard_fields(self) -> None:
        """ProcessHits must fill eventID, trackID, edep, position, time."""
        code = await _get_generated_code()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]

        assert "SetEventID" in source
        assert "SetTrackID" in source
        assert "SetEdep" in source
        assert "SetPosition" in source
        assert "SetTime" in source

    async def test_hit_header_has_include_guard(self) -> None:
        code = await _get_generated_code()
        header = code["SensitiveDetectorManager::Hit.hh"]
        assert "#ifndef HIT_HH" in header
        assert "#define HIT_HH" in header
        assert "#endif" in header

    async def test_sd_header_has_include_guard(self) -> None:
        code = await _get_generated_code()
        header = code["SensitiveDetectorManager::SensitiveDetectorManager.hh"]
        assert "#ifndef SENSITIVE_DETECTOR_MANAGER_HH" in header
        assert "#endif" in header


class TestSDCppStatic:
    """Static C++ quality checks."""

    async def test_no_empty_includes(self) -> None:
        code = await _get_generated_code()
        for fname, content in code.items():
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#include"):
                    assert len(stripped) > len("#include"), (
                        f"Empty include in {fname}:{line_no}"
                    )

    async def test_no_using_namespace_std(self) -> None:
        code = await _get_generated_code()
        for fname, content in code.items():
            assert "using namespace std" not in content, fname

    async def test_source_includes_own_header_first(self) -> None:
        code = await _get_generated_code()
        for fname, content in code.items():
            if not fname.endswith(".cc"):
                continue
            includes = [
                l.strip() for l in content.splitlines()
                if l.strip().startswith("#include")
            ]
            if includes:
                # First include should be the module's own header
                assert "Hit.hh" in includes[0] or "SensitiveDetectorManager.hh" in includes[0], (
                    f"{fname}: first include must be own header, got: {includes[0]}"
                )

    async def test_hit_class_has_allocator(self) -> None:
        """Hit class must have operator new/delete with G4Allocator."""
        code = await _get_generated_code()
        header = code["SensitiveDetectorManager::Hit.hh"]

        assert "operator new" in header
        assert "operator delete" in header
        assert "G4Allocator<Hit>" in header

    async def test_sd_source_includes_g4step(self) -> None:
        """SD source must include G4Step.hh for ProcessHits."""
        code = await _get_generated_code()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]
        assert "G4Step.hh" in source

    async def test_sd_source_includes_touchable_history(self) -> None:
        """SD source must include G4TouchableHistory.hh."""
        code = await _get_generated_code()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]
        assert "G4TouchableHistory.hh" in source

    async def test_no_bare_g4int_in_hit(self) -> None:
        """Hit class must use int, not G4int."""
        code = await _get_generated_code()
        header = code["SensitiveDetectorManager::Hit.hh"]

        for line in header.splitlines():
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            assert not re.search(r'\bG4int\b', stripped), (
                f"Hit.hh: bare G4int: {stripped}"
            )
