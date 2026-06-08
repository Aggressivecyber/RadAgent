"""Geometry module hard gate."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_geometry_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for geometry module."""
    return run_hard_gate_checks(
        module_name="geometry",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=[
            "G4ParticleGun",
            "SensitiveDetector",
            "SetSensitiveDetector",
        ],
    )
