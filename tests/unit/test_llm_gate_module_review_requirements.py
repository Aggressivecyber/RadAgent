from __future__ import annotations

from agent_core.g4_codegen.module_gates.llm_gate_base import _module_review_requirements


def test_output_manager_llm_gate_allows_record_step_contract() -> None:
    requirements = "\n".join(_module_review_requirements("output_manager"))

    assert "RecordStep(const G4Step*)" in requirements
    assert "Do not fail OutputManager" in requirements
    assert "WriteEvent(const G4Event*)" in requirements
