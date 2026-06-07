"""Sensitive detector module hard gate."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_sensitive_detector_hard_gate(
    generated_files: list[GeneratedModuleFile],
) -> ModuleGateResult:
    """Run hard gate checks for sensitive detector module."""
    return run_hard_gate_checks(
        module_name="sensitive_detector",
        generated_files=generated_files,
        forbidden_patterns=["G4ParticleGun"],
    )
