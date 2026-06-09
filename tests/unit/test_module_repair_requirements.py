from __future__ import annotations

from agent_core.g4_codegen.module_agents.output_manager_agent import OUTPUT_SYSTEM_PROMPT
from agent_core.g4_codegen.repair.module_repair_loop import _module_repair_requirements


def test_output_manager_repair_requirements_include_stable_action_interface() -> None:
    requirements = "\n".join(_module_repair_requirements("output_manager"))

    assert "RecordStep(const G4Step*)" in requirements
    assert "WriteEvent(const G4Event* event)" in requirements
    assert "ScoringManager" in requirements
    assert "SetEventDoseGy(G4double doseGy)" in requirements
    assert "hard-coded 0.0" in requirements


def test_output_manager_prompt_forbids_hard_coded_zero_dose() -> None:
    assert "dose_Gy 不得写死为 0.0" in OUTPUT_SYSTEM_PROMPT
    assert "SetEventDoseGy(G4double doseGy)" in OUTPUT_SYSTEM_PROMPT
    assert "WriteEvent(const G4Event* event, G4double edepMeV, G4double doseGy)" in (
        OUTPUT_SYSTEM_PROMPT
    )
