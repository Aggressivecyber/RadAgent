"""Tests for subgraph compilation and structure."""

from __future__ import annotations

import types


def test_context_subgraph_compiles() -> None:
    """Context subgraph should compile without errors."""
    from agent_core.context import build_context_subgraph

    graph = build_context_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_task_planning_subgraph_compiles() -> None:
    """Task planning subgraph should compile without errors."""
    from agent_core.planning import build_task_planning_subgraph

    graph = build_task_planning_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_g4_modeling_subgraph_compiles() -> None:
    """G4 modeling subgraph should compile without errors."""
    from agent_core.graph.subgraphs.g4_modeling_graph import build_g4_modeling_subgraph

    graph = build_g4_modeling_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_g4_codegen_subgraph_compiles() -> None:
    """G4 codegen subgraph should compile without errors."""
    from agent_core.graph.subgraphs.g4_codegen_graph import build_g4_codegen_subgraph

    graph = build_g4_codegen_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_patch_subgraph_compiles() -> None:
    """Patch subgraph should compile without errors."""
    from agent_core.patching import build_patch_subgraph

    graph = build_patch_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_gate_subgraph_compiles() -> None:
    """Gate subgraph should compile without errors."""
    from agent_core.gates import build_gate_validation_subgraph

    graph = build_gate_validation_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_artifact_subgraph_compiles() -> None:
    """Artifact subgraph should compile without errors."""
    from agent_core.artifacts import build_artifact_subgraph

    graph = build_artifact_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_report_subgraph_compiles() -> None:
    """Report subgraph should compile without errors."""
    from agent_core.reports import build_report_subgraph

    graph = build_report_subgraph()
    compiled = graph.compile()
    assert compiled is not None


def test_main_graph_compiles() -> None:
    """Main graph should compile without errors."""
    from agent_core.graph.main_graph import compile_main_graph

    graph = compile_main_graph()
    assert graph is not None


def test_human_confirmation_compiled_graph_exposes_all_registered_nodes() -> None:
    """Human-confirmation conditional routes should render as reachable graph edges."""
    from agent_core.graph.subgraphs.human_confirmation_graph import (
        build_human_confirmation_subgraph,
    )

    mermaid = build_human_confirmation_subgraph().get_graph().draw_mermaid()

    for node_id in (
        "build_proposed_model_completion",
        "generate_confirmation_request",
        "human_interrupt_node",
        "parse_confirmation_response",
        "merge_user_confirmation",
        "validate_confirmation_completeness",
    ):
        assert node_id in mermaid

    assert "human_interrupt_node -.-> parse_confirmation_response" in mermaid
    assert "merge_user_confirmation -.-> validate_confirmation_completeness" in mermaid
    assert "validate_confirmation_completeness -.-> generate_confirmation_request" in mermaid


async def test_human_confirmation_wrapper_preserves_unconfirmed_count(monkeypatch) -> None:
    """Main graph wrapper must keep the subgraph's exact unconfirmed count."""
    from agent_core.graph.main_graph import build_subgraph_nodes

    class _FakeCompiled:
        async def ainvoke(self, state):
            return {
                "confirmation_status": "approved",
                "confirmation_request_path": "request.json",
                "confirmation_response_path": "response.json",
                "confirmation_record_path": "record.json",
                "confirmed_model_plan_path": "plan.json",
                "unconfirmed_assumptions_count": 3,
                "requires_human_confirmation": True,
            }

    fake_module = types.SimpleNamespace(
        build_human_confirmation_subgraph=lambda: _FakeCompiled()
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "agent_core.graph.subgraphs.human_confirmation_graph",
        fake_module,
    )

    result = await build_subgraph_nodes()["human_confirmation"]({"job_id": "job"})

    assert result["unconfirmed_assumptions_count"] == 3


async def test_codegen_wrapper_passes_confirmation_status(monkeypatch) -> None:
    """Main graph wrapper must pass confirmation_status into the codegen state."""
    from agent_core.graph.main_graph import build_subgraph_nodes

    captured_state = {}

    class _FakeCompiled:
        async def ainvoke(self, state):
            captured_state.update(state)
            return {"g4_codegen_status": "passed"}

    class _FakeGraph:
        def compile(self):
            return _FakeCompiled()

    fake_module = types.SimpleNamespace(build_g4_codegen_subgraph=lambda: _FakeGraph())
    monkeypatch.setitem(
        __import__("sys").modules,
        "agent_core.graph.subgraphs.g4_codegen_graph",
        fake_module,
    )

    await build_subgraph_nodes()["g4_codegen"](
        {
            "job_id": "job",
            "confirmation_status": "approved",
            "confirmation_record_path": "record.json",
            "confirmed_model_plan_path": "plan.json",
        }
    )

    assert captured_state["human_confirmation_status"] == "approved"
    assert captured_state["confirmation_record_path"] == "record.json"
    assert captured_state["confirmed_model_plan_path"] == "plan.json"


async def test_g4_modeling_loads_confirmed_requirement_plan(tmp_path, monkeypatch) -> None:
    """G4 modeling must receive the MAX-reviewed user-approved requirements."""
    from agent_core.g4_modeling.subgraph_io import load_task_spec

    task_spec_path = tmp_path / "task_spec.json"
    confirmed_path = tmp_path / "confirmed_requirement_plan.json"
    task_spec_path.write_text(
        '{"particle":{"type":"proton","energy_MeV":150}}',
        encoding="utf-8",
    )
    confirmed_path.write_text(
        '{"schema_version":"confirmed_requirement_plan_v1","user_response":{"feedback":"Use 1 mm bins."}}',
        encoding="utf-8",
    )

    result = await load_task_spec(
        {
            "task_spec_path": str(task_spec_path),
            "confirmed_requirement_plan_path": str(confirmed_path),
        }
    )

    assert result["confirmed_requirement_plan"]["user_response"]["feedback"] == "Use 1 mm bins."
    assert result["task_spec"]["confirmed_requirement_plan"]["user_response"]["feedback"] == "Use 1 mm bins."
    assert result["task_spec"]["metadata"]["confirmed_requirement_plan_path"] == str(confirmed_path)


def test_main_state_has_path_fields() -> None:
    """Main state should have path-based fields, not inline data."""
    from agent_core.graph.main_state import RadAgentMainState

    annotations = RadAgentMainState.__annotations__
    # Must have path fields
    path_fields = [
        "context_report_path",
        "evidence_map_path",
        "task_spec_path",
        "g4_model_ir_path",
        "component_specs_dir",
        "construction_ledger_path",
        "code_module_plan_path",
        "proposed_patch_path",
        "generated_code_dir",
        "gate_results_path",
        "review_artifact_dir",
        "final_report_path",
    ]
    for field in path_fields:
        assert field in annotations, f"Missing path field: {field}"

    # Must NOT have inline data fields
    forbidden = [
        "g4_model_ir",  # should be path, not dict
        "simulation_ir",  # old field
        "rag_context",  # should be in file
        "g4_context",  # old naming
        "tcad_context",  # removed
        "spice_context",  # removed
    ]
    for field in forbidden:
        assert field not in annotations, f"Forbidden inline field present: {field}"
