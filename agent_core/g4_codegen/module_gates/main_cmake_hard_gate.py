"""Main/CMake module hard gate."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_main_cmake_hard_gate(
    generated_files: list[GeneratedModuleFile],
) -> ModuleGateResult:
    """Run hard gate checks for main/CMake module."""
    return run_hard_gate_checks(
        module_name="main_cmake",
        generated_files=generated_files,
        forbidden_patterns=[],
    )
