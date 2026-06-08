"""P0-10: Hard gate rejects ModuleAgentResult with status='failed'."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _valid_file() -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path="include/Test.hh",
        new_content="#pragma once\n",
        generated_by="test_module_agent",
        module_name="test",
        rationale="test",
    )


def test_failed_status_rejected():
    result = run_hard_gate_checks("test", [_valid_file()], module_status="failed")
    assert result.status == "fail"
    assert any("module_status" in c["check"] for c in result.checks)


def test_generated_status_accepted():
    result = run_hard_gate_checks("test", [_valid_file()], module_status="generated")
    assert result.status == "pass"


def test_repaired_status_accepted():
    result = run_hard_gate_checks("test", [_valid_file()], module_status="repaired")
    assert result.status == "pass"


def test_unknown_status_rejected():
    result = run_hard_gate_checks("test", [_valid_file()], module_status="unknown")
    assert result.status == "fail"


def test_none_status_not_checked():
    """When module_status is None, skip the check (backward compat)."""
    result = run_hard_gate_checks("test", [_valid_file()], module_status=None)
    assert result.status == "pass"
