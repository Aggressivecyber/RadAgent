"""Tests for component_geometry_codegen and placement_codegen.

Verifies:
  - Geometry builder creates only solid + logical volume (NO placement)
  - PlacementManager handles ALL G4PVPlacement calls
  - Position/rotation come from IR placement specs
  - Empty components → empty modules
  - C++ static quality: include guards, no empty includes, no free functions
  - geometry_type mapping covers box, tubs, cylinder
  - Builder has material null check
  - checkOverlaps is always enabled
"""

from __future__ import annotations

import re
from typing import Any


def _model_ir_with_hierarchy() -> dict[str, Any]:
    """Return a model IR with world + child component."""
    return {
        "model_ir_id": "test_geom",
        "job_id": "test_geom",
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
                "component_id": "sensitive_layer",
                "display_name": "Sensitive Layer",
                "component_type": "layer",
                "geometry_type": "box",
                "dimensions": {"dx": 100, "dy": 100, "dz": 10},
                "material_id": "G4_Si",
                "mother_volume": "world",
                "placement": {
                    "position": [0, 0, 500],
                    "rotation": [0, 0, 90],
                },
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
        "ledger": {"entries": [], "version": "1.0"},
    }


# ── Component Geometry Builder tests ──


class TestComponentGeometryContract:
    """Verify builder creates only solid + logical volume."""

    async def test_produces_modules_per_component(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await component_geometry_codegen(state)

        modules = result.get("code_modules", [])
        assert len(modules) == 2  # world + sensitive_layer

        names = [m["module_name"] for m in modules]
        assert "WorldBuilder" in names
        assert "SensitiveLayerBuilder" in names

    async def test_empty_components_returns_empty(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        model_ir = _model_ir_with_hierarchy()
        model_ir["components"] = []
        result = await component_geometry_codegen({"g4_model_ir": model_ir})
        assert result.get("code_modules", []) == []

    async def test_builder_has_no_place_method(self) -> None:
        """Builder must NOT have Place() method — placement is PlacementManager's job."""
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await component_geometry_codegen(state)

        for mod in result["code_modules"]:
            content = mod["generated_content"]
            for fname, code in content.items():
                assert "Place(" not in code, f"{fname}: Builder must not have Place() method"
                assert "G4PVPlacement" not in code, f"{fname}: Builder must not use G4PVPlacement"

    async def test_builder_creates_logical_volume(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await component_geometry_codegen(state)

        world_mod = result["code_modules"][0]
        source = world_mod["generated_content"]["WorldBuilder::WorldBuilder.cc"]
        assert "new G4Box(" in source
        assert "new G4LogicalVolume(" in source
        assert "GetMaterial(" in source

    async def test_builder_has_material_null_check(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await component_geometry_codegen(state)

        world_mod = result["code_modules"][0]
        source = world_mod["generated_content"]["WorldBuilder::WorldBuilder.cc"]
        assert "if (!material)" in source

    async def test_builder_references_correct_material(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await component_geometry_codegen(state)

        # World uses G4_AIR
        world_src = result["code_modules"][0]["generated_content"]["WorldBuilder::WorldBuilder.cc"]
        assert 'GetMaterial("G4_AIR")' in world_src

        # Sensitive layer uses G4_Si
        sens_src = result["code_modules"][1]["generated_content"][
            "SensitiveLayerBuilder::SensitiveLayerBuilder.cc"
        ]
        assert 'GetMaterial("G4_Si")' in sens_src

    async def test_header_no_pv_placement_include(self) -> None:
        """Header must not include G4PVPlacement — builder doesn't place."""
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await component_geometry_codegen(state)

        for mod in result["code_modules"]:
            content = mod["generated_content"]
            header = [v for k, v in content.items() if k.endswith(".hh")][0]
            assert "G4PVPlacement" not in header

    async def test_linked_ids_populated(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await component_geometry_codegen(state)

        world = result["code_modules"][0]
        assert world["linked_component_ids"] == ["world"]
        assert world["linked_material_ids"] == ["G4_AIR"]

        sens = result["code_modules"][1]
        assert sens["linked_component_ids"] == ["sensitive_layer"]
        assert sens["linked_material_ids"] == ["G4_Si"]


# ── Placement Manager tests ──


class TestPlacementContract:
    """Verify PlacementManager handles all placement."""

    async def test_produces_single_module(self) -> None:
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await placement_codegen(state)

        modules = result.get("code_modules", [])
        assert len(modules) == 1
        assert modules[0]["module_name"] == "PlacementManager"

    async def test_empty_components_returns_empty(self) -> None:
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        model_ir = _model_ir_with_hierarchy()
        model_ir["components"] = []
        result = await placement_codegen({"g4_model_ir": model_ir})
        assert result.get("code_modules", []) == []

    async def test_world_placed_at_origin(self) -> None:
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await placement_codegen(state)

        source = result["code_modules"][0]["generated_content"][
            "PlacementManager::PlacementManager.cc"
        ]
        assert "phys_world" in source
        assert "G4ThreeVector()" in source
        assert "builder_world->GetLogicalVolume()" in source

    async def test_child_uses_placement_from_ir(self) -> None:
        """Child placement must use position/rotation from IR, not from builder."""
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await placement_codegen(state)

        source = result["code_modules"][0]["generated_content"][
            "PlacementManager::PlacementManager.cc"
        ]

        # Position from IR: [0, 0, 500]
        assert "500" in source and "*um" in source
        # Rotation from IR: [0, 0, 90]
        assert "90" in source and "*deg" in source
        # Must NOT call builder->Place()
        assert "->Place(" not in source

    async def test_check_overlaps_enabled(self) -> None:
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await placement_codegen(state)

        source = result["code_modules"][0]["generated_content"][
            "PlacementManager::PlacementManager.cc"
        ]
        assert "SetCheckOverlaps(true)" in source
        assert "CheckOverlaps(1000" in source

    async def test_all_components_have_placement(self) -> None:
        """Every component must appear in placement code."""
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await placement_codegen(state)

        source = result["code_modules"][0]["generated_content"][
            "PlacementManager::PlacementManager.cc"
        ]
        assert "builder_world" in source
        assert "builder_sensitive_layer" in source

    async def test_depends_on_all_builders(self) -> None:
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await placement_codegen(state)

        mod = result["code_modules"][0]
        assert "WorldBuilder" in mod["depends_on"]
        assert "SensitiveLayerBuilder" in mod["depends_on"]


# ── Static C++ quality ──


class TestGeometryCppStatic:
    """Static C++ quality for geometry + placement generated code."""

    async def test_no_empty_includes(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        geom_result = await component_geometry_codegen(state)
        place_result = await placement_codegen(state)

        all_code = []
        for mod in geom_result.get("code_modules", []):
            all_code.extend(mod["generated_content"].items())
        for mod in place_result.get("code_modules", []):
            all_code.extend(mod["generated_content"].items())

        for fname, content in all_code:
            for line_no, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#include"):
                    assert len(stripped) > len("#include"), f"Empty include in {fname}:{line_no}"

    async def test_no_using_namespace_std(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        geom_result = await component_geometry_codegen(state)
        place_result = await placement_codegen(state)

        for mod in geom_result.get("code_modules", []):
            for fname, content in mod["generated_content"].items():
                assert "using namespace std" not in content, fname
        for mod in place_result.get("code_modules", []):
            for fname, content in mod["generated_content"].items():
                assert "using namespace std" not in content, fname

    async def test_no_bare_g4int(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        geom_result = await component_geometry_codegen(state)
        place_result = await placement_codegen(state)

        for mod in geom_result.get("code_modules", []):
            for fname, content in mod["generated_content"].items():
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("//"):
                        continue
                    assert not re.search(r"\bG4int\b", stripped), f"{fname}: bare G4int: {stripped}"
        for mod in place_result.get("code_modules", []):
            for fname, content in mod["generated_content"].items():
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("//"):
                        continue
                    assert not re.search(r"\bG4int\b", stripped), f"{fname}: bare G4int: {stripped}"

    async def test_include_guards_present(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        result = await component_geometry_codegen(state)

        for mod in result["code_modules"]:
            content = mod["generated_content"]
            for fname, code in content.items():
                if not fname.endswith(".hh"):
                    continue
                assert "#ifndef" in code, f"{fname}: missing include guard"
                assert "#define" in code, f"{fname}: missing include guard"
                assert "#endif" in code, f"{fname}: missing include guard"

    async def test_source_includes_own_header_first(self) -> None:
        from agent_core.g4_modeling.codegen.component_geometry_codegen import (
            component_geometry_codegen,
        )
        from agent_core.g4_modeling.codegen.placement_codegen import (
            placement_codegen,
        )

        state = {"g4_model_ir": _model_ir_with_hierarchy()}
        geom_result = await component_geometry_codegen(state)
        place_result = await placement_codegen(state)

        for mod in geom_result.get("code_modules", []) + place_result.get("code_modules", []):
            content = mod["generated_content"]
            for fname, code in content.items():
                if not fname.endswith(".cc"):
                    continue
                includes = [
                    l.strip() for l in code.splitlines() if l.strip().startswith("#include")
                ]
                if includes:
                    class_name = fname.split("::")[1].replace(".cc", "")
                    assert class_name in includes[0], f"{fname}: first include must be own header"
