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
            r"\bEventData\b",
            r"G4VUserEventInformation",
            r"GetUserInformation\s*\(",
            r"SetUserInformation\s*\(",
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

    has_one_arg_write_event_decl = bool(
        re.search(
            r"\bWriteEvent\s*\(\s*const\s+G4Event\s*\*\s*(?:[A-Za-z_]\w*|/\*.*?\*/)?\s*\)\s*;",
            header,
        )
    )
    has_one_arg_write_event_def = bool(
        re.search(
            r"\bOutputManager::WriteEvent\s*\(\s*const\s+G4Event\s*\*\s*(?:[A-Za-z_]\w*|/\*.*?\*/)?"
            r"\s*\)",
            source,
        )
    )
    signature_checks = [
        {
            "check": "output_manager_declares_one_arg_write_event",
            "status": "pass" if has_one_arg_write_event_decl else "fail",
            "message": "OutputManager.hh must declare void WriteEvent(const G4Event* event)",
        },
        {
            "check": "output_manager_defines_one_arg_write_event",
            "status": "pass" if has_one_arg_write_event_def else "fail",
            "message": (
                "OutputManager.cc must define void OutputManager::WriteEvent(const G4Event*)"
            ),
        },
    ]
    result.checks.extend(signature_checks)
    for check in signature_checks:
        if check["status"] == "fail":
            result.status = "fail"
            result.errors.append(check["message"])

    uses_g4_output_dir = bool(
        re.search(r"\b(?:std::)?getenv\s*\(\s*\"G4_OUTPUT_DIR\"\s*\)", source)
    )
    contract_filenames = {
        "output.csv": "runtime event table consumed by Geant4Runner",
        "run_summary.json": "runtime summary consumed by Geant4Runner",
        "metadata.json": "runtime metadata consumed by Geant4Runner",
    }
    artifact_checks = [
        {
            "check": "output_manager_uses_g4_output_dir",
            "status": "pass" if uses_g4_output_dir else "fail",
            "message": "OutputManager.cc must read G4_OUTPUT_DIR for runtime artifacts",
        },
    ]
    for filename, purpose in contract_filenames.items():
        artifact_checks.append(
            {
                "check": f"output_manager_writes_{filename}",
                "status": "pass" if filename in source else "fail",
                "message": f"OutputManager.cc must write fixed {filename} for {purpose}",
            }
        )

    has_stable_event_header = _has_output_csv_header_contract(source)
    artifact_checks.append(
        {
            "check": "output_manager_output_csv_header_contract",
            "status": "pass" if has_stable_event_header else "fail",
            "message": "output.csv header must include EventID,edep_MeV,dose_Gy",
        }
    )

    uses_job_prefixed_artifact_name = bool(
        re.search(
            r"_(?:events\.csv|run_summary\.json|metadata\.json)",
            source,
        )
    )
    artifact_checks.append(
        {
            "check": "output_manager_uses_fixed_artifact_names",
            "status": "fail" if uses_job_prefixed_artifact_name else "pass",
            "message": (
                "OutputManager.cc must not use job-prefixed artifact filenames; "
                "write output.csv, run_summary.json, and metadata.json"
            ),
        }
    )

    result.checks.extend(artifact_checks)
    for check in artifact_checks:
        if check["status"] == "fail":
            result.status = "fail"
            result.errors.append(check["message"])


def _has_output_csv_header_contract(source: str) -> bool:
    if "EventID,edep_MeV,dose_Gy" in source:
        return True
    compact = re.sub(r"\s+", "", source)
    return bool(
        re.search(
            r'"EventID".{0,120}"edep_MeV".{0,120}"dose_Gy"',
            compact,
        )
    )
