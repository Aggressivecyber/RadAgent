from __future__ import annotations

from agent_core.g4_codegen.repair.module_repair_loop import _module_repair_requirements


def test_output_manager_repair_requirements_include_stable_action_interface() -> None:
    requirements = "\n".join(_module_repair_requirements("output_manager"))

    assert "RecordStep(const G4Step*)" in requirements
    assert "WriteEvent(const G4Event* event)" in requirements
    assert "ScoringManager" in requirements
