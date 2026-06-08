"""Placement module hard gate."""

from __future__ import annotations

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
