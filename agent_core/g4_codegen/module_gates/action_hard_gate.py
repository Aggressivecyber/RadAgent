"""Action initialization module hard gate."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleGateResult


def run_action_hard_gate(
    generated_files: list[GeneratedModuleFile],
    module_status: str | None = None,
) -> ModuleGateResult:
    """Run hard gate checks for action initialization module."""
    result = run_hard_gate_checks(
        module_name="action_initialization",
        generated_files=generated_files,
        module_status=module_status,
        forbidden_patterns=[],
    )
    _append_output_manager_call_checks(result, generated_files)
    return result


def _append_output_manager_call_checks(
    result: ModuleGateResult,
    generated_files: list[GeneratedModuleFile],
) -> None:
    forbidden_calls = [
        "BeginOfRun(",
        "EndOfRun(",
        "BeginOfEvent(",
        "EndOfEvent(",
        "RecordEventData(",
    ]
    checks: list[dict[str, str]] = []
    for f in generated_files:
        content = f.new_content
        if "OutputManager::Instance()" not in content:
            continue
        for call in forbidden_calls:
            checks.append(
                {
                    "check": f"action_no_output_manager_{call.rstrip('(')}",
                    "status": "fail" if f"->{call}" in content else "pass",
                    "message": f"{f.path} must not call OutputManager::{call.rstrip('(')}",
                }
            )

    result.checks.extend(checks)
    for check in checks:
        if check["status"] == "fail":
            result.status = "fail"
            result.errors.append(check["message"])
