"""G4 Codegen Subgraph schemas."""

from __future__ import annotations

from typing import Any, TypedDict


class G4CodegenSubgraphState(TypedDict, total=False):
    """State for the G4 Codegen Subgraph.

    Reads Model IR (not user query) and generates modular C++.
    Compatible with existing codegen nodes.
    """

    # Input paths
    job_id: str
    g4_model_ir_path: str
    component_specs_dir: str
    construction_ledger_path: str

    # Loaded data
    g4_model_ir: dict[str, Any]
    code_modules: list[dict[str, Any]]

    # Generated code (populated by codegen nodes)
    code_patch: dict[str, Any]
    proposed_patch: dict[str, Any]

    # Output paths
    code_module_plan_path: str
    proposed_patch_path: str
    generated_code_dir: str
    g4_codegen_status: str

    # Control
    current_node: str
    errors: list[str]
    retry_count: int
    patch_applied_at: str
