"""Output manager module hard gate."""

from __future__ import annotations

import re

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_output_manager_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for output manager module."""
    result = run_hard_gate_checks(
        module_name="output_manager",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=[
            "G4PVPlacement",
            "G4ParticleGun",
            r'#include\s+[<"]ScoringManager\.hh[>"]',
            r"\bScoringManager\s*::",
            r"\bScoringManager\s*\*",
            r"\bScoringManager\s+",
        ],
    )
    _append_output_manager_interface_checks(result, generated_files)
    return result


def _append_output_manager_interface_checks(
    result: ModuleGateResult,
    generated_files: list[GeneratedModuleFile],
) -> None:
    by_path = {f.path: f.new_content for f in generated_files}
    header = by_path.get("include/OutputManager.hh", "")
    source = by_path.get("src/OutputManager.cc", "")
    if not header:
        return
    required_methods = [
        ("Instance", "static OutputManager* Instance"),
        ("BeginRun", "BeginRun("),
        ("EndRun", "EndRun("),
        ("BeginEvent", "BeginEvent("),
        ("EndEvent", "EndEvent("),
        ("RecordStep", "RecordStep("),
        ("WriteEvent", "WriteEvent("),
        ("SetRunMetadata", "SetRunMetadata("),
        ("WriteRunSummary", "WriteRunSummary("),
        ("WriteMetadata", "WriteMetadata("),
    ]
    checks: list[dict[str, str]] = []
    for method_name, declaration_marker in required_methods:
        checks.append(
            {
                "check": f"output_manager_declares_{method_name}",
                "status": "pass" if declaration_marker in header else "fail",
                "message": f"OutputManager.hh must declare {method_name}",
            }
        )
        if method_name == "Instance":
            definition_marker = "OutputManager::Instance("
        else:
            definition_marker = f"OutputManager::{method_name}("
        checks.append(
            {
                "check": f"output_manager_defines_{method_name}",
                "status": "pass" if definition_marker in source else "fail",
                "message": f"OutputManager.cc must define {method_name}",
            }
        )

    has_g4_types = all(
        marker in header
        for marker in (
            "G4Run",
            "G4Event",
            "G4Step",
        )
    )
    checks.append(
        {
            "check": "output_manager_declares_geant4_action_types",
            "status": "pass" if has_g4_types else "fail",
            "message": (
                "OutputManager.hh must forward declare or include G4Run, "
                "G4Event, and G4Step"
            ),
        }
    )

    if "G4String" in header:
        has_g4string_include = bool(
            re.search(r"#include\s+[<\"]G4String\.hh[>\"]", header)
        )
        checks.append(
            {
                "check": "output_manager_g4string_header_include",
                "status": "pass" if has_g4string_include else "fail",
                "message": "OutputManager.hh must include G4String.hh when declaring G4String",
            }
        )

    result.checks.extend(checks)
    for check in checks:
        if check["status"] == "fail":
            result.status = "fail"
            result.errors.append(check["message"])
