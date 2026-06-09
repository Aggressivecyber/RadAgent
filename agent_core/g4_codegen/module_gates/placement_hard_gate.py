"""Placement module hard gate."""

from __future__ import annotations

import re

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_placement_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for placement module."""
    result = run_hard_gate_checks(
        module_name="placement",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=[
            "G4ParticleGun",
            "G4VSensitiveDetector",
            "G4NistManager",
            "DetectorConstruction",
        ],
    )
    _append_placement_file_scope_checks(result, generated_files)
    _append_placement_api_checks(result, generated_files)
    return result


def _append_placement_file_scope_checks(
    result: ModuleGateResult,
    generated_files: list[GeneratedModuleFile],
) -> None:
    allowed_paths = {"include/PlacementManager.hh", "src/PlacementManager.cc"}
    checks: list[dict[str, str]] = []
    for f in generated_files:
        checks.append(
            {
                "check": "placement_allowed_file_scope",
                "status": "pass" if f.path in allowed_paths else "fail",
                "message": "Placement module may only generate PlacementManager.hh/cc",
            }
        )
    result.checks.extend(checks)
    for check in checks:
        if check["status"] == "fail":
            result.status = "fail"
            result.errors.append(check["message"])


def _append_placement_api_checks(
    result: ModuleGateResult,
    generated_files: list[GeneratedModuleFile],
) -> None:
    checks: list[dict[str, str]] = []
    errors: list[str] = []

    for f in generated_files:
        content = f.new_content
        if not f.path.endswith((".hh", ".cc")):
            continue

        forward_declares_rotation_matrix_alias = bool(
            f.path.endswith((".hh", ".h"))
            and re.search(r"\bclass\s+G4RotationMatrix\s*;", content)
        )
        checks.append(
            {
                "check": "placement_header_does_not_forward_declare_g4rotationmatrix",
                "status": (
                    "fail" if forward_declares_rotation_matrix_alias else "pass"
                ),
                "message": (
                    "PlacementManager.hh must include G4RotationMatrix.hh instead of "
                    "forward declaring class G4RotationMatrix"
                ),
            }
        )
        if forward_declares_rotation_matrix_alias:
            errors.append(
                f"{f.path}: include G4RotationMatrix.hh; Geant4 defines "
                "G4RotationMatrix as an alias, not a forward-declarable class"
            )

        has_const_rotation = bool(
            re.search(r"\bconst\s+G4RotationMatrix\s*\*\s+\w+", content)
        )
        checks.append(
            {
                "check": "placement_rotation_pointer_not_const",
                "status": "fail" if has_const_rotation else "pass",
                "message": (
                    "G4PVPlacement rotation overload requires G4RotationMatrix*, "
                    "not const G4RotationMatrix*"
                ),
            }
        )
        if has_const_rotation:
            errors.append(f"{f.path}: use G4RotationMatrix* for placement rotation parameters")

        const_transform_params = re.findall(
            r"\bconst\s+G4Transform3D\s*&\s+([A-Za-z_]\w*)\b",
            content,
        )
        direct_const_transform = any(
            re.search(rf"new\s+G4PVPlacement\s*\(\s*{re.escape(param)}\b", content)
            for param in const_transform_params
        )
        checks.append(
            {
                "check": "placement_transform_passed_as_nonconst_copy",
                "status": "fail" if direct_const_transform else "pass",
                "message": (
                    "Do not pass const G4Transform3D& directly to G4PVPlacement; "
                    "make a non-const local copy first"
                ),
            }
        )
        if direct_const_transform:
            errors.append(
                f"{f.path}: copy const G4Transform3D& into a non-const local before G4PVPlacement"
            )
        place_mother_physical = bool(
            re.search(
                r"\bPlace\w*\s*\([^;{)]*G4VPhysicalVolume\s*\*\s*mother",
                content,
                re.DOTALL,
            )
        )
        checks.append(
            {
                "check": "placement_mother_parameter_is_logical_volume",
                "status": "fail" if place_mother_physical else "pass",
                "message": (
                    "PlacementManager placement API mother parameter must be "
                    "G4LogicalVolume*, not G4VPhysicalVolume*"
                ),
            }
        )
        if place_mother_physical:
            errors.append(
                f"{f.path}: use G4LogicalVolume* mother for G4PVPlacement mother logical"
            )
        extra_constructor_many_flag = bool(
            re.search(
                r"new\s+G4PVPlacement\s*\([^;]*\bmother\s*,\s*false\s*,\s*many\s*,"
                r"\s*copyNo\s*,\s*checkOverlaps",
                content,
                re.DOTALL,
            )
        )
        checks.append(
            {
                "check": "placement_g4pvplacement_uses_eight_argument_logical_mother_constructor",
                "status": "fail" if extra_constructor_many_flag else "pass",
                "message": (
                    "G4PVPlacement logical-mother constructor must be called as "
                    "new G4PVPlacement(rotation, position, logical, name, mother, "
                    "many, copyNo, checkOverlaps), without an extra false argument"
                ),
            }
        )
        if extra_constructor_many_flag:
            errors.append(
                f"{f.path}: remove the extra false argument before many in "
                "new G4PVPlacement(rotation, position, logical, name, mother, "
                "many, copyNo, checkOverlaps)"
            )
        if f.path.endswith((".hh", ".h")) and "G4PVPlacement" in content:
            declares_g4pvplacement = (
                "#include <G4PVPlacement.hh>" in content
                or '#include "G4PVPlacement.hh"' in content
                or re.search(r"\bclass\s+G4PVPlacement\s*;", content)
            )
            checks.append(
                {
                    "check": "placement_header_declares_g4pvplacement",
                    "status": "pass" if declares_g4pvplacement else "fail",
                    "message": (
                        "PlacementManager.hh must include G4PVPlacement.hh or forward "
                        "declare class G4PVPlacement when declarations use G4PVPlacement*"
                    ),
                }
            )
            if not declares_g4pvplacement:
                errors.append(
                    f"{f.path}: declare class G4PVPlacement or include G4PVPlacement.hh"
                )
        if f.path.endswith(".cc") and re.search(
            r"\bG4PVPlacement\*\s+PlacementManager::Place\s*\([^)]*\)\s*\{"
            r"(?:(?!\n\}).)*\breturn\s+[^;]*PlaceVolume\s*\(",
            content,
            re.DOTALL,
        ):
            checks.append(
                {
                    "check": "placement_static_place_return_type_matches_placevolume",
                    "status": "fail",
                    "message": (
                        "PlacementManager::Place must return G4VPhysicalVolume* when it "
                        "returns PlaceVolume(...); do not force a G4PVPlacement* return"
                    ),
                }
            )
            errors.append(
                f"{f.path}: return G4VPhysicalVolume* from PlacementManager::Place "
                "when delegating to PlaceVolume"
            )

        if f.path.endswith(".cc"):
            dereferences_logical_volume = bool(
                re.search(r"\b(?:logical|mother|[A-Za-z_]\w*)\s*->\s*GetName\s*\(", content)
                or re.search(
                    r"\bG4LogicalVolume\s*\*\s*[A-Za-z_]\w*[^;{]*\{[^}]*->",
                    content,
                    re.DOTALL,
                )
            )
            has_logical_volume_include = bool(
                re.search(r"#include\s+[<\"]G4LogicalVolume\.hh[>\"]", content)
            )
            checks.append(
                {
                    "check": "placement_dereference_logical_volume_requires_full_header",
                    "status": (
                        "pass"
                        if not dereferences_logical_volume or has_logical_volume_include
                        else "fail"
                    ),
                    "message": (
                        "PlacementManager.cc must include G4LogicalVolume.hh before "
                        "dereferencing G4LogicalVolume*"
                    ),
                }
            )
            if dereferences_logical_volume and not has_logical_volume_include:
                errors.append(
                    f"{f.path}: include G4LogicalVolume.hh before calling "
                    "G4LogicalVolume methods such as GetName()"
                )

    result.checks.extend(checks)
    if errors:
        result.status = "fail"
        result.errors.extend(errors)
