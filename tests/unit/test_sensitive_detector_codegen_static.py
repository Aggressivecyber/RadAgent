"""Static C++ quality checks for SensitiveDetector generated code.

Verifies:
  - No empty includes
  - SD class defined BEFORE Attach method (C++ compilation order)
  - Required includes present
  - std::map type correct in header
  - Uses G4String for constructor params
"""

from __future__ import annotations

from typing import Any

import pytest


def _make_model_ir_with_sd() -> dict[str, Any]:
    return {
        "model_ir_id": "test_sd_v1",
        "job_id": "test_sd",
        "target_system": "Test Detector",
        "components": [
            {
                "component_id": "world",
                "display_name": "World",
                "component_type": "world",
                "geometry_type": "box",
                "dimensions": {"dx": 100.0, "dy": 100.0, "dz": 100.0},
                "material_id": "G4_AIR",
                "source_evidence": ["test"],
            },
            {
                "component_id": "sensor",
                "display_name": "Sensor",
                "component_type": "volume",
                "geometry_type": "box",
                "dimensions": {"dx": 10.0, "dy": 10.0, "dz": 2.0},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "source_evidence": ["test"],
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
                "beam": {"position": [0, 0, 0], "direction": [0, 0, -1]},
                "source_evidence": ["test"],
            }
        ],
        "physics": {
            "physics_list": "QGSP_BIC_HP",
            "selection_reasoning": "Standard for proton simulation testing",
            "source_evidence": ["test"],
        },
        "scoring": [
            {
                "scoring_id": "edep_sensor",
                "scoring_type": "region",
                "quantities": ["edep_MeV"],
                "region_scores": [{"region_component_id": "sensor", "quantity": "edep_MeV"}],
                "source_evidence": ["test"],
            }
        ],
        "sensitive_detectors": [
            {
                "sd_id": "sensor_sd",
                "name": "SensorSD",
                "collection_name": "SensorHitsCollection",
                "linked_component_ids": ["sensor"],
                "hit_fields": [
                    {"name": "edep_MeV", "dtype": "double"},
                    {"name": "position", "dtype": "double"},
                ],
                "source_evidence": ["test"],
            }
        ],
    }


async def _get_generated() -> dict[str, str]:
    from agent_core.g4_modeling.codegen.sensitive_detector_codegen import (
        sensitive_detector_codegen,
    )
    result = await sensitive_detector_codegen({"g4_model_ir": _make_model_ir_with_sd()})
    return result["code_modules"][0]["generated_content"]


class TestSensitiveDetectorCppStatic:
    @pytest.mark.asyncio
    async def test_no_empty_includes(self) -> None:
        code = await _get_generated()
        for fname, content in code.items():
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("#include"):
                    assert len(stripped) > len("#include"), f"Empty include in {fname}: {stripped}"

    @pytest.mark.asyncio
    async def test_header_has_required_includes(self) -> None:
        code = await _get_generated()
        header = code["SensitiveDetectorManager::SensitiveDetectorManager.hh"]
        assert '#include "G4VSensitiveDetector.hh"' in header
        assert '#include "Hit.hh"' in header
        assert "#include <map>" in header
        assert "#include <string>" in header

    @pytest.mark.asyncio
    async def test_header_map_type_correct(self) -> None:
        code = await _get_generated()
        header = code["SensitiveDetectorManager::SensitiveDetectorManager.hh"]
        assert "std::map<std::string, G4VSensitiveDetector*> detectors_;" in header

    @pytest.mark.asyncio
    async def test_source_has_required_includes(self) -> None:
        code = await _get_generated()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]
        assert '#include "SensitiveDetectorManager.hh"' in source
        assert '#include "G4SDManager.hh"' in source
        assert '#include "G4Step.hh"' in source
        assert '#include "G4LogicalVolumeStore.hh"' in source
        assert '#include "G4RunManager.hh"' in source
        assert '#include "G4Event.hh"' in source

    @pytest.mark.asyncio
    async def test_sd_class_declared_before_attach(self) -> None:
        """Concrete SD class must be defined BEFORE Attach method that uses it."""
        code = await _get_generated()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]
        # SensorSdSD class must appear before AttachSensorSd method
        class_idx = source.index("class SensorSdSD")
        attach_idx = source.index("void SensitiveDetectorManager::AttachSensorSd")
        assert class_idx < attach_idx, (
            f"SD class at pos {class_idx} must be before Attach at pos {attach_idx}"
        )

    @pytest.mark.asyncio
    async def test_sd_constructor_uses_g4string(self) -> None:
        """Constructor must use G4String, not std::string."""
        code = await _get_generated()
        source = code["SensitiveDetectorManager::SensitiveDetectorManager.cc"]
        assert "const G4String& name, const G4String& collectionName" in source

    @pytest.mark.asyncio
    async def test_include_guard(self) -> None:
        code = await _get_generated()
        header = code["SensitiveDetectorManager::SensitiveDetectorManager.hh"]
        assert "#ifndef SENSITIVE_DETECTOR_MANAGER_HH" in header
        assert "#define SENSITIVE_DETECTOR_MANAGER_HH" in header
        assert "#endif" in header
