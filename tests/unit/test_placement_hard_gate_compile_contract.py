from __future__ import annotations

from agent_core.g4_codegen.module_gates.placement_hard_gate import run_placement_hard_gate
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _file(path: str, content: str) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path=path,
        operation="create_or_replace",
        new_content=content,
        generated_by="placement_module_agent",
        module_name="placement",
        rationale="test",
    )


def test_placement_hard_gate_rejects_missing_g4pvplacement_declaration() -> None:
    result = run_placement_hard_gate(
        [
            _file(
                "include/PlacementManager.hh",
                "#pragma once\n"
                "class G4LogicalVolume;\n"
                "class G4RotationMatrix;\n"
                "class PlacementManager {\n"
                "public:\n"
                "  static G4PVPlacement* Place(G4LogicalVolume*, G4RotationMatrix*);\n"
                "};\n",
            ),
            _file("src/PlacementManager.cc", '#include "PlacementManager.hh"\n'),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4PVPlacement" in error for error in result.errors)


def test_placement_hard_gate_accepts_g4pvplacement_forward_declaration() -> None:
    result = run_placement_hard_gate(
        [
            _file(
                "include/PlacementManager.hh",
                "#pragma once\n"
                '#include "G4RotationMatrix.hh"\n'
                "class G4PVPlacement;\n"
                "class G4LogicalVolume;\n"
                "class PlacementManager {\n"
                "public:\n"
                "  static G4PVPlacement* Place(G4LogicalVolume*, G4RotationMatrix*);\n"
                "};\n",
            ),
            _file("src/PlacementManager.cc", '#include "PlacementManager.hh"\n'),
        ],
        module_status="generated",
    )

    assert not any("G4PVPlacement" in error for error in result.errors)


def test_placement_hard_gate_rejects_placevolume_return_type_mismatch() -> None:
    result = run_placement_hard_gate(
        [
            _file(
                "include/PlacementManager.hh",
                "#pragma once\n"
                '#include "G4RotationMatrix.hh"\n'
                "class G4PVPlacement;\n"
                "class G4LogicalVolume;\n"
                "class PlacementManager {\n"
                "public:\n"
                "  G4VPhysicalVolume* PlaceVolume(G4RotationMatrix*);\n"
                "  static G4PVPlacement* Place(G4LogicalVolume*, G4RotationMatrix*);\n"
                "};\n",
            ),
            _file(
                "src/PlacementManager.cc",
                '#include "PlacementManager.hh"\n'
                "G4PVPlacement* PlacementManager::Place(G4LogicalVolume*, "
                "G4RotationMatrix* rotation) {\n"
                "  return PlaceVolume(rotation);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4VPhysicalVolume" in error for error in result.errors)


def test_placement_hard_gate_rejects_physical_volume_mother_parameter() -> None:
    result = run_placement_hard_gate(
        [
            _file(
                "include/PlacementManager.hh",
                "#pragma once\n"
                '#include "G4RotationMatrix.hh"\n'
                "class G4VPhysicalVolume;\n"
                "class G4LogicalVolume;\n"
                "class G4ThreeVector;\n"
                "class PlacementManager {\n"
                "public:\n"
                "  G4VPhysicalVolume* PlaceVolume(G4RotationMatrix*, "
                "const G4ThreeVector&, G4LogicalVolume*, const G4String&, "
                "G4VPhysicalVolume* mother, G4bool, G4int);\n"
                "};\n",
            ),
            _file("src/PlacementManager.cc", '#include "PlacementManager.hh"\n'),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4LogicalVolume* mother" in error for error in result.errors)


def test_placement_hard_gate_rejects_static_place_physical_volume_mother() -> None:
    result = run_placement_hard_gate(
        [
            _file(
                "include/PlacementManager.hh",
                "#pragma once\n"
                '#include "G4RotationMatrix.hh"\n'
                "class G4VPhysicalVolume;\n"
                "class G4LogicalVolume;\n"
                "class G4ThreeVector;\n"
                "class PlacementManager {\n"
                "public:\n"
                "  static G4VPhysicalVolume* Place(G4LogicalVolume* logical, "
                "const G4ThreeVector& position, G4RotationMatrix* rotation, "
                "G4VPhysicalVolume* mother, G4bool checkOverlaps);\n"
                "};\n",
            ),
            _file(
                "src/PlacementManager.cc",
                '#include "PlacementManager.hh"\n'
                "G4VPhysicalVolume* PlacementManager::Place("
                "G4LogicalVolume* logical, const G4ThreeVector& position, "
                "G4RotationMatrix* rotation, G4VPhysicalVolume* mother, "
                "G4bool checkOverlaps) { return nullptr; }\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4LogicalVolume* mother" in error for error in result.errors)


def test_placement_hard_gate_rejects_extra_false_in_g4pvplacement_constructor() -> None:
    result = run_placement_hard_gate(
        [
            _file(
                "include/PlacementManager.hh",
                "#pragma once\n"
                '#include "G4RotationMatrix.hh"\n'
                "class G4LogicalVolume;\n"
                "class G4ThreeVector;\n"
                "class G4String;\n"
                "class G4VPhysicalVolume;\n"
                "class PlacementManager {\n"
                "public:\n"
                "  static G4VPhysicalVolume* PlaceVolume("
                "G4RotationMatrix* rotation, const G4ThreeVector& position, "
                "G4LogicalVolume* logical, const G4String& name, "
                "G4LogicalVolume* mother, G4bool many, G4int copyNo, "
                "G4bool checkOverlaps);\n"
                "};\n",
            ),
            _file(
                "src/PlacementManager.cc",
                '#include "PlacementManager.hh"\n'
                '#include "G4PVPlacement.hh"\n'
                "G4VPhysicalVolume* PlacementManager::PlaceVolume("
                "G4RotationMatrix* rotation, const G4ThreeVector& position, "
                "G4LogicalVolume* logical, const G4String& name, "
                "G4LogicalVolume* mother, G4bool many, G4int copyNo, "
                "G4bool checkOverlaps) {\n"
                "  return new G4PVPlacement(rotation, position, logical, name, "
                "mother, false, many, copyNo, checkOverlaps);\n"
                "}\n",
            ),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("extra false argument" in error for error in result.errors)


def test_placement_hard_gate_rejects_g4rotationmatrix_forward_declaration() -> None:
    result = run_placement_hard_gate(
        [
            _file(
                "include/PlacementManager.hh",
                "#pragma once\n"
                "class G4RotationMatrix;\n"
                "class PlacementManager {\n"
                "public:\n"
                "  void Place(G4RotationMatrix* rotation);\n"
                "};\n",
            ),
            _file("src/PlacementManager.cc", '#include "PlacementManager.hh"\n'),
        ],
        module_status="generated",
    )

    assert result.status == "fail"
    assert any("G4RotationMatrix.hh" in error for error in result.errors)
