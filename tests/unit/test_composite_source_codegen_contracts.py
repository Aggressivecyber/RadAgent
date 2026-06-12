"""Codegen contract checks for composite radiation field sources."""

from __future__ import annotations

from agent_core.g4_codegen.module_agents.beam_physics_agent import (
    BEAM_PHYSICS_SYSTEM_PROMPT,
)
from agent_core.g4_codegen.planners.module_contract_builder import MODULE_DEFINITIONS
from agent_core.g4_modeling.prompts.requirement_capture_prompt import (
    GEOMETRY_DECOMPOSITION_PROMPT,
    PHYSICS_SELECTION_PROMPT,
    REQUIREMENT_CAPTURE_PROMPT,
)


def test_beam_physics_prompt_requires_all_ir_sources() -> None:
    prompt = BEAM_PHYSICS_SYSTEM_PROMPT.lower()

    assert "all sources" in prompt
    assert "relative_weight" in prompt
    assert "multi-source" in prompt
    assert "json" not in prompt


def test_beam_physics_contract_requires_composite_source_fidelity() -> None:
    responsibilities = " ".join(MODULE_DEFINITIONS["beam_physics"]["responsibilities"]).lower()

    assert "all g4modelir sources" in responsibilities
    assert "relative_weight" in responsibilities
    assert "multi-source" in responsibilities


def test_modeling_prompts_preserve_composite_radiation_field_inputs() -> None:
    requirement_prompt = REQUIREMENT_CAPTURE_PROMPT.lower()
    physics_prompt = PHYSICS_SELECTION_PROMPT.lower()

    assert "one required_sources item per" in requirement_prompt
    assert "source_id" in requirement_prompt
    assert "relative_weight" in requirement_prompt
    assert "all source components" in physics_prompt
    assert "composite radiation field" in physics_prompt


def test_geometry_prompt_matches_full_length_component_schema() -> None:
    prompt = GEOMETRY_DECOMPOSITION_PROMPT.lower()

    assert "full lengths" in prompt
    assert "half-lengths for box" not in prompt
    assert "dx=half_width" not in prompt
