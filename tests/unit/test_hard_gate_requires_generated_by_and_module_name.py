"""Hard gate checks generated_by and module_name fields."""

from __future__ import annotations

from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks
from agent_core.g4_codegen.schemas import GeneratedModuleFile


def _make_file(
    generated_by: str = "material_module_agent",
    module_name: str = "material",
) -> GeneratedModuleFile:
    return GeneratedModuleFile(
        path="include/Test.hh",
        new_content="#pragma once\n",
        generated_by=generated_by,
        module_name=module_name,
        rationale="test",
    )


def test_correct_generated_by_passes():
    result = run_hard_gate_checks("material", [_make_file()])
    gen_checks = [c for c in result.checks if c["check"] == "generated_by"]
    assert gen_checks
    assert gen_checks[0]["status"] == "pass"


def test_wrong_generated_by_fails():
    result = run_hard_gate_checks("material", [_make_file(generated_by="wrong_agent")])
    gen_checks = [c for c in result.checks if c["check"] == "generated_by"]
    assert gen_checks
    assert gen_checks[0]["status"] == "fail"
    assert result.status == "fail"


def test_correct_module_name_passes():
    result = run_hard_gate_checks("material", [_make_file()])
    mod_checks = [c for c in result.checks if c["check"] == "module_name"]
    assert mod_checks
    assert mod_checks[0]["status"] == "pass"


def test_wrong_module_name_fails():
    result = run_hard_gate_checks("material", [_make_file(module_name="wrong")])
    mod_checks = [c for c in result.checks if c["check"] == "module_name"]
    assert mod_checks
    assert mod_checks[0]["status"] == "fail"
    assert result.status == "fail"
