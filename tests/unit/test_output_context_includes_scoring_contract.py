"""P0-22: output_manager context includes scoring contract."""

from __future__ import annotations

from agent_core.g4_codegen.module_agents.module_context_builder import (
    build_module_context,
)


def _minimal_contract():
    return {
        "module_name": "output_manager",
        "module_type": "output_manager",
        "responsibilities": ["WriteResults"],
        "output_files": ["include/OutputManager.hh"],
        "required_symbols": ["OutputManager"],
        "dependencies": ["scoring"],
    }


def _minimal_ir():
    return {
        "model_ir_id": "test",
        "job_id": "job_001",
        "scoring": [{"scoring_id": "edep_score"}],
        "sources": [{"source_id": "src1"}],
    }


def test_output_context_has_scoring():
    ctx = build_module_context(
        module_name="output_manager",
        module_contract=_minimal_contract(),
        g4_model_ir=_minimal_ir(),
        codegen_plan={"required_modules": ["output_manager"]},
        geometry_strategy_plan={"global_strategy": "agent_generated_geometry"},
        code_architecture_plan={"classes": []},
        job_id="job_001",
    )
    ir_subset = ctx["g4_model_ir_subset"]
    assert "scoring" in ir_subset
    assert len(ir_subset["scoring"]) == 1


def test_output_context_has_sources():
    ctx = build_module_context(
        module_name="output_manager",
        module_contract=_minimal_contract(),
        g4_model_ir=_minimal_ir(),
        codegen_plan={"required_modules": ["output_manager"]},
        geometry_strategy_plan={"global_strategy": "agent_generated_geometry"},
        code_architecture_plan={"classes": []},
        job_id="job_001",
    )
    ir_subset = ctx["g4_model_ir_subset"]
    assert "sources" in ir_subset
