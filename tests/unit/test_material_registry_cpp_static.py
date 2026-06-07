"""Static C++ quality checks for MaterialRegistry generated code.

Verifies:
  - No empty includes
  - std::map<std::string, G4Material*> type correct
  - G4SystemOfUnits.hh in source
  - Custom materials use AddElement pattern
"""

from __future__ import annotations

from typing import Any

import pytest


def _make_model_ir_with_custom_material() -> dict[str, Any]:
    return {
        "model_ir_id": "test_mat_v1",
        "job_id": "test_mat",
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
            }
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
                "material_id": "SiO2",
                "name": "SiO2",
                "classification": "custom",
                "density_g_cm3": 2.2,
                "composition": [
                    {"element": "Si", "fraction": 1},
                    {"element": "O", "fraction": 2},
                ],
                "source_evidence": ["user_spec"],
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
                "scoring_id": "edep",
                "scoring_type": "region",
                "quantities": ["edep_MeV"],
                "region_scores": [{"region_component_id": "world", "quantity": "edep_MeV"}],
                "source_evidence": ["test"],
            }
        ],
    }


async def _get_generated() -> dict[str, str]:
    from agent_core.g4_modeling.codegen.material_registry_codegen import (
        material_registry_codegen,
    )
    result = await material_registry_codegen({"g4_model_ir": _make_model_ir_with_custom_material()})
    return result["code_modules"][0]["generated_content"]


class TestMaterialRegistryCppStatic:
    @pytest.mark.asyncio
    async def test_header_no_empty_includes(self) -> None:
        code = await _get_generated()
        header = code["MaterialRegistry::MaterialRegistry.hh"]
        for line in header.splitlines():
            stripped = line.strip()
            if stripped.startswith("#include"):
                assert len(stripped) > len("#include"), f"Empty include: {stripped}"

    @pytest.mark.asyncio
    async def test_source_no_empty_includes(self) -> None:
        code = await _get_generated()
        source = code["MaterialRegistry::MaterialRegistry.cc"]
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("#include"):
                assert len(stripped) > len("#include"), f"Empty include: {stripped}"

    @pytest.mark.asyncio
    async def test_header_has_required_includes(self) -> None:
        code = await _get_generated()
        header = code["MaterialRegistry::MaterialRegistry.hh"]
        assert '#include "G4Material.hh"' in header
        assert '#include "G4NistManager.hh"' in header
        assert "#include <map>" in header
        assert "#include <string>" in header

    @pytest.mark.asyncio
    async def test_registry_map_type_correct(self) -> None:
        code = await _get_generated()
        header = code["MaterialRegistry::MaterialRegistry.hh"]
        assert "std::map<std::string, G4Material*> registry_;" in header

    @pytest.mark.asyncio
    async def test_source_has_system_of_units(self) -> None:
        code = await _get_generated()
        source = code["MaterialRegistry::MaterialRegistry.cc"]
        assert '#include "G4SystemOfUnits.hh"' in source

    @pytest.mark.asyncio
    async def test_nist_material_registration(self) -> None:
        code = await _get_generated()
        source = code["MaterialRegistry::MaterialRegistry.cc"]
        assert 'FindOrBuildMaterial("G4_AIR")' in source
        assert 'registry_["G4_AIR"]' in source

    @pytest.mark.asyncio
    async def test_custom_material_add_element(self) -> None:
        code = await _get_generated()
        source = code["MaterialRegistry::MaterialRegistry.cc"]
        # SiO2 custom material must use AddElement
        assert "AddElement(el_Si, 1" in source
        assert "AddElement(el_O, 2" in source
        assert "2.2 * g/cm3" in source

    @pytest.mark.asyncio
    async def test_include_guard(self) -> None:
        code = await _get_generated()
        header = code["MaterialRegistry::MaterialRegistry.hh"]
        assert "#ifndef MATERIAL_REGISTRY_HH" in header
        assert "#define MATERIAL_REGISTRY_HH" in header
        assert "#endif" in header
