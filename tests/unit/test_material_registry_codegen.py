"""Tests for MaterialRegistry codegen — contract and static C++ quality.

Verifies:
  - Empty materials → empty code_modules
  - NIST materials produce correct getter methods
  - Custom materials produce correct Define methods with null checks
  - Include guards, order, no empty includes
  - No forbidden patterns (using namespace std, bare G4int, etc.)
  - Variable names don't shadow parameters
  - material_config.json is valid JSON with correct fields
"""

from __future__ import annotations

import json
import re
from typing import Any


def _minimal_model_ir_with_materials() -> dict[str, Any]:
    """Return a model IR with both NIST and custom materials."""
    return {
        "model_ir_id": "test_material_codegen",
        "job_id": "test_material_codegen",
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
                "dimensions": {"dx": 1000, "dy": 1000, "dz": 1000},
                "material_id": "G4_AIR",
                "source_evidence": ["standard"],
            },
        ],
        "materials": [
            {
                "material_id": "silicon",
                "name": "Silicon",
                "classification": "nist",
                "nist_name": "G4_Si",
                "density_g_cm3": 2.33,
                "source_evidence": ["NIST"],
            },
            {
                "material_id": "air",
                "name": "Air",
                "classification": "nist",
                "nist_name": "G4_AIR",
                "density_g_cm3": 0.001214,
                "source_evidence": ["NIST"],
            },
            {
                "material_id": "sio2",
                "name": "Silicon Dioxide",
                "classification": "custom",
                "composition": [
                    {"element": "Si", "fraction": 0.467},
                    {"element": "O", "fraction": 0.533},
                ],
                "density_g_cm3": 2.65,
                "source_evidence": ["user_spec"],
            },
        ],
        "sources": [
            {
                "source_id": "proton",
                "particle_type": "proton",
                "energy": {"value": 10.0, "unit": "MeV"},
                "beam": {"position": [0, 0, 500], "direction": [0, 0, -1]},
                "source_evidence": ["user_spec"],
            },
        ],
        "physics": {
            "physics_list": "QGSP_BIC",
            "selection_reasoning": "Standard EM for proton simulation",
            "source_evidence": ["geant4_guide"],
        },
        "scoring": [],
        "ledger": {"entries": [], "version": "1.0"},
    }


async def _get_generated_code() -> dict[str, str]:
    """Run codegen and return {filename: content}."""
    from agent_core.g4_modeling.codegen.material_registry_codegen import (
        material_registry_codegen,
    )

    state = {"g4_model_ir": _minimal_model_ir_with_materials()}
    result = await material_registry_codegen(state)
    return result["code_modules"][0]["generated_content"]


# ── Contract tests ──


class TestMaterialRegistryContract:
    """Verify codegen output structure and content."""

    async def test_produces_module_with_all_files(self) -> None:
        from agent_core.g4_modeling.codegen.material_registry_codegen import (
            material_registry_codegen,
        )

        state = {"g4_model_ir": _minimal_model_ir_with_materials()}
        result = await material_registry_codegen(state)

        modules = result.get("code_modules", [])
        assert len(modules) == 1
        mod = modules[0]
        assert mod["module_name"] == "MaterialRegistry"
        assert "MaterialRegistry.cc" in mod["source_files"]
        assert "MaterialRegistry.hh" in mod["header_files"]
        assert "material_config.json" in mod["config_files"]

    async def test_empty_materials_returns_empty(self) -> None:
        from agent_core.g4_modeling.codegen.material_registry_codegen import (
            material_registry_codegen,
        )

        model_ir = _minimal_model_ir_with_materials()
        model_ir["materials"] = []
        result = await material_registry_codegen({"g4_model_ir": model_ir})
        assert result.get("code_modules", []) == []

    async def test_linked_material_ids_populated(self) -> None:
        from agent_core.g4_modeling.codegen.material_registry_codegen import (
            material_registry_codegen,
        )

        state = {"g4_model_ir": _minimal_model_ir_with_materials()}
        result = await material_registry_codegen(state)
        mod = result["code_modules"][0]
        assert "silicon" in mod["linked_material_ids"]
        assert "air" in mod["linked_material_ids"]
        assert "sio2" in mod["linked_material_ids"]

    async def test_nist_getter_methods_generated(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        # NIST material getters must exist
        assert "MaterialRegistry::GetSi()" in source
        assert "MaterialRegistry::GetAir()" in source

    async def test_custom_define_methods_generated(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        # Custom material define method
        assert "MaterialRegistry::DefineSio2(" in source

    async def test_nist_registration_in_define_all(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        # NIST materials must be registered via FindOrBuildMaterial
        assert 'FindOrBuildMaterial("G4_Si")' in source
        assert 'FindOrBuildMaterial("G4_AIR")' in source

    async def test_custom_registration_in_define_all(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        # Custom materials must call their Define method
        assert "DefineSio2(nist)" in source

    async def test_custom_material_uses_g_cm3_unit(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        # Must use g/cm3 Geant4 unit, not raw number
        assert "g/cm3" in source

    async def test_custom_material_has_element_null_checks(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        # Must check FindOrBuildElement result
        assert "if (!el_Si)" in source
        assert "if (!el_O)" in source

    async def test_custom_material_adds_elements(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        # Must add elements to material
        assert "->AddElement(el_Si, 0.467)" in source
        assert "->AddElement(el_O, 0.533)" in source

    async def test_config_json_is_valid(self) -> None:
        code = await _get_generated_code()
        config = json.loads(code["MaterialRegistry::material_config.json"])

        assert "materials" in config
        assert len(config["materials"]) == 3
        for m in config["materials"]:
            assert "material_id" in m
            assert "classification" in m
            assert "density_g_cm3" in m


# ── Static C++ quality tests ──


class TestMaterialRegistryCppStatic:
    """Static C++ quality checks for generated MaterialRegistry code."""

    async def test_include_guard_present(self) -> None:
        code = await _get_generated_code()
        header = code["MaterialRegistry::MaterialRegistry.hh"]

        assert "#ifndef MATERIAL_REGISTRY_HH" in header
        assert "#define MATERIAL_REGISTRY_HH" in header
        lines = [l.strip() for l in header.splitlines() if l.strip()]
        assert lines[-1] == "#endif"

    async def test_source_includes_own_header_first(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        include_lines = [
            l.strip() for l in source.splitlines()
            if l.strip().startswith("#include")
        ]
        assert len(include_lines) > 0
        first = include_lines[0]
        assert '"MaterialRegistry.hh"' in first

    async def test_geant4_includes_before_stl(self) -> None:
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        lines = source.splitlines()
        g4_idx = None
        stl_idx = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("#include"):
                continue
            if stripped.startswith("#include <G4") or stripped.startswith("#include \"G4"):
                if g4_idx is None:
                    g4_idx = i
            elif stripped.startswith("#include <") and not stripped.startswith("#include <G4"):
                if stl_idx is None:
                    stl_idx = i

        # Geant4 includes must come before STL includes
        if g4_idx is not None and stl_idx is not None:
            assert g4_idx < stl_idx

    async def test_no_empty_includes(self) -> None:
        code = await _get_generated_code()
        for fname, content in code.items():
            if fname.endswith(".json"):
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#include"):
                    assert len(stripped) > len("#include"), (
                        f"Empty include in {fname}:{line_no}"
                    )
                    has_angle = "<" in stripped and ">" in stripped
                    has_quote = '"' in stripped
                    assert has_angle or has_quote, (
                        f"Malformed include in {fname}:{line_no}: {stripped}"
                    )

    async def test_no_using_namespace_std(self) -> None:
        code = await _get_generated_code()
        for fname, content in code.items():
            if fname.endswith(".json"):
                continue
            assert "using namespace std" not in content, (
                f"{fname}: forbidden 'using namespace std'"
            )

    async def test_no_bare_g4int(self) -> None:
        code = await _get_generated_code()
        for fname, content in code.items():
            if fname.endswith(".json"):
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                assert not re.search(r'\bG4int\b', stripped), (
                    f"{fname}:{line_no}: bare G4int, use int: {stripped}"
                )

    async def test_no_free_functions(self) -> None:
        """All methods must be qualified as MaterialRegistry::."""
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        for line_no, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            # Match bare function definitions (not in comments)
            if stripped.startswith("//"):
                continue
            if re.match(r'^(void|G4Material\*)\s+\w+\s*\(', stripped):
                assert "MaterialRegistry::" in stripped, (
                    f"Line {line_no}: Unqualified free function: {stripped}"
                )

    async def test_no_variable_shadowing_material_id(self) -> None:
        """Local variables must use mat_ prefix, not raw material_id."""
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        # The old pattern used bare material_id as local var name
        # e.g. "auto* sio2 = new G4Material(..." is fine now,
        # but "auto* {mat.material_id} = ..." without mat_ prefix is bad.
        # Check that mat_ prefix is used for new G4Material
        for line in source.splitlines():
            stripped = line.strip()
            if "new G4Material(" in stripped:
                assert "mat_" in stripped, (
                    f"Must use mat_ prefix for material variable: {stripped}"
                )

    async def test_getmaterial_method_exists(self) -> None:
        code = await _get_generated_code()
        header = code["MaterialRegistry::MaterialRegistry.hh"]
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        assert 'GetMaterial(const std::string& id)' in header
        assert 'MaterialRegistry::GetMaterial(const std::string& id)' in source

    async def test_define_all_materials_method(self) -> None:
        code = await _get_generated_code()
        header = code["MaterialRegistry::MaterialRegistry.hh"]
        source = code["MaterialRegistry::MaterialRegistry.cc"]

        assert "void DefineAllMaterials();" in header
        assert "MaterialRegistry::DefineAllMaterials()" in source

    async def test_system_of_units_included(self) -> None:
        """Source must include G4SystemOfUnits.hh for g/cm3."""
        code = await _get_generated_code()
        source = code["MaterialRegistry::MaterialRegistry.cc"]
        assert "G4SystemOfUnits.hh" in source
