"""G4 Modeling Subgraph state — bridges old node interface to subgraph.

The existing g4_modeling nodes use RadiationAgentState. This module
provides a TypedDict that satisfies those nodes' state expectations,
so we can reuse the existing validated nodes without rewriting them.
"""

from __future__ import annotations

from typing import Any, TypedDict


class G4ModelingSubgraphState(TypedDict, total=False):
    """State for the G4 Modeling Subgraph.

    Compatible with existing g4_modeling nodes that expect
    RadiationAgentState-style access patterns.
    """

    # Input
    job_id: str
    user_query: str
    task_spec_path: str
    evidence_map_path: str
    confirmed_requirement_plan_path: str

    # Internal state (populated by nodes, consumed by downstream nodes)
    g4_model_ir: dict[str, Any]
    evidence_pack: dict[str, Any]
    model_scope_guard_result: dict[str, Any]
    model_ir_errors: list[str]
    model_review_report: str
    construction_ledger: list[dict[str, Any]]
    code_modules: list[dict[str, Any]]

    # Task spec (loaded from file)
    task_spec: dict[str, Any]
    simulation_plan: dict[str, Any]
    confirmed_requirement_plan: dict[str, Any]

    # Output paths
    g4_model_ir_path: str
    component_specs_dir: str
    interfaces_path: str
    construction_ledger_path: str
    model_review_report_path: str
    g4_modeling_status: str
    human_confirmation_required: bool

    # Control
    current_node: str
    errors: list[str]
    retry_count: int
    modeling_mode: str
