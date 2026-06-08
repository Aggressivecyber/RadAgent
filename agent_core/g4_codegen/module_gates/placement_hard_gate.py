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

        direct_const_transform = bool(
            re.search(
                r"new\s+G4PVPlacement\s*\(\s*(?:[A-Za-z_]\w*::)?\w*transform\b",
                content,
                re.IGNORECASE,
            )
            and re.search(r"\bconst\s+G4Transform3D\s*&\s+\w*transform\b", content)
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

    result.checks.extend(checks)
    if errors:
        result.status = "fail"
        result.errors.extend(errors)
