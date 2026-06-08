"""Material module hard gate."""

from __future__ import annotations

import re

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_material_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for material module."""
    result = run_hard_gate_checks(
        module_name="material",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=[
            "G4PVPlacement",
            "G4ParticleGun",
            "G4VSensitiveDetector",
        ],
    )
    _append_material_contract_checks(result, generated_files)
    return result


def _append_material_contract_checks(
    result: ModuleGateResult,
    generated_files: list[GeneratedModuleFile],
) -> None:
    files_by_path = {f.path: f for f in generated_files}
    header = files_by_path.get("include/MaterialRegistry.hh")
    source = files_by_path.get("src/MaterialRegistry.cc")
    checks: list[dict[str, str]] = []
    errors: list[str] = []

    for required in ("include/MaterialRegistry.hh", "src/MaterialRegistry.cc"):
        checks.append(
            {
                "check": "material_required_file",
                "status": "pass" if required in files_by_path else "fail",
                "message": f"Material module must generate {required}",
            }
        )
        if required not in files_by_path:
            errors.append(f"Missing mandatory material file {required}")

    for f in generated_files:
        if re.search(
            r"\b(for now|should handle|skip|silently|placeholder)\b",
            f.new_content,
            re.IGNORECASE,
        ):
            checks.append(
                {
                    "check": "material_no_placeholder_error_handling",
                    "status": "fail",
                    "message": (
                        "MaterialRegistry must not use placeholder or silent-skip "
                        "handling for missing materials"
                    ),
                }
            )
            errors.append(f"{f.path}: replace placeholder material error handling")

    header_text = header.new_content if header else ""
    source_text = source.new_content if source else ""
    custom_api_declared = bool(
        re.search(r"\b(AddCustomMaterial|RegisterCustomMaterial)\s*\(", header_text)
    )
    custom_api_defined = bool(
        re.search(
            r"\bMaterialRegistry::(AddCustomMaterial|RegisterCustomMaterial)\s*\(",
            source_text,
        )
    )
    checks.append(
        {
            "check": "material_custom_material_api",
            "status": "pass" if custom_api_declared and custom_api_defined else "fail",
            "message": (
                "MaterialRegistry must declare and define AddCustomMaterial or "
                "RegisterCustomMaterial"
            ),
        }
    )
    if not custom_api_declared or not custom_api_defined:
        errors.append(
            "MaterialRegistry must expose and implement AddCustomMaterial/RegisterCustomMaterial"
        )

    creates_or_accepts_custom_material = bool(
        re.search(r"\bnew\s+G4Material\b|\bG4Material\s*\*", source_text)
    )
    checks.append(
        {
            "check": "material_custom_material_storage",
            "status": "pass" if creates_or_accepts_custom_material else "fail",
            "message": "MaterialRegistry must support registering custom G4Material instances",
        }
    )
    if not creates_or_accepts_custom_material:
        errors.append("MaterialRegistry must store custom G4Material instances")

    has_g4string_getter = bool(
        re.search(r"\bGetMaterial\s*\(\s*const\s+G4String\s*&", header_text)
    )
    has_std_string_getter = bool(
        re.search(r"\bGetMaterial\s*\(\s*const\s+std::string\s*&", header_text)
    )
    checks.append(
        {
            "check": "material_no_ambiguous_getmaterial_overloads",
            "status": "fail" if has_g4string_getter and has_std_string_getter else "pass",
            "message": (
                "Do not overload GetMaterial with both G4String and std::string; "
                "string literals become ambiguous"
            ),
        }
    )
    if has_g4string_getter and has_std_string_getter:
        errors.append("MaterialRegistry has ambiguous GetMaterial overloads")

    result.checks.extend(checks)
    if errors:
        result.status = "fail"
        result.errors.extend(errors)
