"""LangGraph state definition for the Radiation Simulation Agent."""

from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict


def _last_value(existing: Any, new: Any) -> Any:
    """Reducer that keeps only the latest value (last-write-wins).

    Used for state keys that may receive concurrent updates from
    parallel fan-out nodes (e.g. RAG retrieval).
    """
    return new


class RadiationAgentState(TypedDict, total=False):
    """Complete state for the radiation simulation agent pipeline."""

    # Job identification
    job_id: str
    user_query: str

    # Parsed task specification
    task_spec: dict[str, Any]
    task_spec_errors: list[str]

    # Simulation intermediate representation
    simulation_ir: dict[str, Any]
    simulation_ir_errors: list[str]

    # RAG routing and context
    rag_route: list[str]
    g4_context: list[dict[str, Any]]
    tcad_context: list[dict[str, Any]]
    spice_context: list[dict[str, Any]]
    web_context: list[dict[str, Any]]
    rag_sufficiency_score: float
    rag_sufficiency_report: dict[str, Any]

    # Planning
    simulation_plan: dict[str, Any]
    code_architecture_plan: dict[str, Any]
    test_plan: dict[str, Any]

    # Code generation
    proposed_patch: dict[str, Any]
    patch_review_result: dict[str, Any]
    applied_patch: dict[str, Any]

    # Gate checks and error handling
    gate_results: list[dict[str, Any]]
    failure_report: dict[str, Any]
    fix_patch: dict[str, Any]
    retry_count: Annotated[int, _last_value]
    max_retries_reached: Annotated[bool, _last_value]

    # Simulation data packages (G4 -> TCAD -> SPICE pipeline)
    g4_output_package: dict[str, Any]
    tcad_input_package: dict[str, Any]
    tcad_output_package: dict[str, Any]
    spice_input_package: dict[str, Any]
    spice_output_package: dict[str, Any]

    # Results
    simulation_results: dict[str, Any]
    data_contract_results: dict[str, Any]
    physics_sanity_results: dict[str, Any]

    # Report
    final_report: str

    # Control flow — uses reducer to survive concurrent writes from fan-out nodes
    current_node: Annotated[str, _last_value]
    errors: Annotated[list[str], add]
