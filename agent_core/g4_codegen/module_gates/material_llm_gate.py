"""material module LLM gate."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_gates.llm_gate_base import run_llm_gate
from agent_core.g4_codegen.schemas import ModuleGateResult


async def run_material_llm_gate(
    module_context: dict[str, Any],
    generated_files_content: list[dict[str, Any]],
    hard_gate_result: dict[str, Any],
) -> ModuleGateResult:
    """Run LLM gate for material module."""
    return await run_llm_gate(
        module_name="material",
        module_context=module_context,
        generated_files_content=generated_files_content,
        hard_gate_result=hard_gate_result,
    )
