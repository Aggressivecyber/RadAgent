"""P0-24: codegen respects acceptance mode."""

from __future__ import annotations

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState


def test_codegen_state_has_run_mode():
    """G4CodegenSubgraphState includes run_mode field."""
    state: G4CodegenSubgraphState = {
        "job_id": "test",
        "run_mode": "acceptance",
        "execution_mode": "mvp1_acceptance",
    }
    assert state["run_mode"] == "acceptance"


def test_codegen_state_has_execution_mode():
    state: G4CodegenSubgraphState = {
        "job_id": "test",
        "run_mode": "dev",
        "execution_mode": "dev_no_geant4_env",
    }
    assert state["execution_mode"] == "dev_no_geant4_env"


def test_codegen_plan_schema_has_requires_human_confirmation():
    from agent_core.g4_codegen.schemas import CodegenPlan

    plan = CodegenPlan(
        scenario_type="semiconductor",
        required_modules=["material", "geometry"],
        module_order=["material", "geometry"],
        requires_human_confirmation=True,
    )
    assert plan.requires_human_confirmation is True
