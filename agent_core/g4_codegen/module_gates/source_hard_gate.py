"""Source module hard gate."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_source_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for source module."""
    result = run_hard_gate_checks(
        module_name="source",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=["G4PVPlacement", "G4VSensitiveDetector"],
    )
    checks = list(result.checks)
    errors = list(result.errors)

    for file_entry in generated_files:
        content = file_entry.new_content
        if "SetParticlePosition" in content and "*cm" in content:
            checks.append(
                {
                    "check": "source_position_uses_global_length_unit",
                    "status": "fail",
                    "message": "Source position must use global length unit mm, not cm",
                }
            )
            errors.append(f"{file_entry.path}: source position must use mm, not cm")

    return ModuleGateResult(
        module_name="source",
        gate_type="hard",
        status="fail" if errors else result.status,
        checks=checks,
        errors=errors,
        warnings=list(result.warnings),
    )
