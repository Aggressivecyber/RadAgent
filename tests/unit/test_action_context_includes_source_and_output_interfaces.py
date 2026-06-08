"""P0-22: action_initialization context includes source and output interfaces."""

from __future__ import annotations

from agent_core.g4_codegen.module_agents.module_context_builder import (
    build_module_context,
)


def _minimal_contract():
    return {
        "module_name": "action_initialization",
        "module_type": "action_initialization",
        "responsibilities": ["Build()"],
        "output_files": ["include/ActionInitialization.hh"],
        "required_symbols": ["ActionInitialization"],
        "dependencies": ["source", "output_manager"],
    }


def _minimal_ir():
    return {
        "model_ir_id": "test",
        "job_id": "job_001",
        "sources": [{"source_id": "src1"}],
        "scoring": [{"scoring_id": "sc1"}],
    }


def _minimal_codegen_plan():
    return {"required_modules": ["action_initialization"]}


def _minimal_geometry_strategy():
    return {"global_strategy": "agent_generated_geometry"}


def _minimal_architecture():
    return {"classes": []}


def test_action_context_has_contract():
    """action_initialization context includes its contract."""
    ctx = build_module_context(
        module_name="action_initialization",
        module_contract=_minimal_contract(),
        g4_model_ir=_minimal_ir(),
        codegen_plan=_minimal_codegen_plan(),
        geometry_strategy_plan=_minimal_geometry_strategy(),
        code_architecture_plan=_minimal_architecture(),
        job_id="job_001",
    )
    assert ctx["module_name"] == "action_initialization"
    assert "module_contract" in ctx


def test_action_context_has_ir_subset():
    """action_initialization context includes IR subset."""
    ctx = build_module_context(
        module_name="action_initialization",
        module_contract=_minimal_contract(),
        g4_model_ir=_minimal_ir(),
        codegen_plan=_minimal_codegen_plan(),
        geometry_strategy_plan=_minimal_geometry_strategy(),
        code_architecture_plan=_minimal_architecture(),
        job_id="job_001",
    )
    ir_subset = ctx["g4_model_ir_subset"]
    assert "model_ir_id" in ir_subset
