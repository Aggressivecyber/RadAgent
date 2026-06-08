"""Physics module hard gate."""

from __future__ import annotations

import re

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_physics_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for physics module."""
    result = run_hard_gate_checks(
        module_name="physics",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=["G4PVPlacement", "G4ParticleGun"],
    )
    _append_physics_ownership_checks(result, generated_files)
    return result


def _append_physics_ownership_checks(
    result: ModuleGateResult,
    generated_files: list[GeneratedModuleFile],
) -> None:
    checks: list[dict[str, str]] = []
    for f in generated_files:
        content = f.new_content
        if "GetReferencePhysList" in content or "fPhysicsList" in content:
            checks.append(
                {
                    "check": "physics_wrapper_does_not_delete_factory_list",
                    "status": "fail" if "delete fPhysicsList" in content else "pass",
                    "message": (
                        "PhysicsListFactoryWrapper must not delete fPhysicsList created "
                        "by G4PhysListFactory"
                    ),
                }
            )
        if f.path.endswith((".hh", ".h")) and any(
            unit in content for unit in ("*mm", "*cm", "*MeV", "*keV")
        ):
            has_units_include = (
                "#include <G4SystemOfUnits.hh>" in content
                or '#include "G4SystemOfUnits.hh"' in content
            )
            checks.append(
                {
                    "check": "physics_header_includes_units_for_default_arguments",
                    "status": "pass" if has_units_include else "fail",
                    "message": (
                        "Physics header must include G4SystemOfUnits.hh when declarations "
                        "use Geant4 unit constants"
                    ),
                }
            )
        if f.path.endswith(".mac") and re.search(
            r"/process/em/setCut\s+[\d.eE+-]+\s+\w+\s+proton\b",
            content,
        ):
            checks.append(
                {
                    "check": "physics_macro_valid_proton_cut_command",
                    "status": "fail",
                    "message": (
                        "Physics macros must not use /process/em/setCut for proton cuts; "
                        "use C++ SetCuts()/SetCutValue or /run/setCutForAGivenParticle"
                    ),
                }
            )
        if f.path.endswith((".cc", ".hh")) and re.search(
            r"CreatePhysicsList\s*\([^)]*\)\s*(?:const\s*)?\{[^{}]*"
            r"G4PhysListFactory\s+\w+\s*;[^{}]*"
            r"\w+\.GetReferencePhysList\s*\(",
            content,
            re.DOTALL,
        ):
            checks.append(
                {
                    "check": "physics_factory_lifetime_not_local",
                    "status": "fail",
                    "message": (
                        "Do not create a local G4PhysListFactory inside CreatePhysicsList(); "
                        "use a member or static factory and cache fPhysicsList"
                    ),
                }
            )

    result.checks.extend(checks)
    for check in checks:
        if check["status"] == "fail":
            result.status = "fail"
            result.errors.append(check["message"])
