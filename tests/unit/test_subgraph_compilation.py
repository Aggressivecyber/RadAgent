"""Tests for subgraph compilation and structure."""

from __future__ import annotations

import json
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


async def test_g4_modeling_applies_confirmed_requirement_plan_to_task_spec(tmp_path) -> None:
    """Approved review choices must become structured modeling inputs."""
    from agent_core.g4_modeling.subgraph_io import load_task_spec

    task_spec_path = tmp_path / "task_spec.json"
    confirmed_path = tmp_path / "confirmed_requirement_plan.json"
    task_spec_path.write_text(
        json.dumps(
            {
                "simulation_scope": ["geant4"],
                "particle": {},
                "energy": {"value": 10.0, "unit": "MeV"},
                "requirements_review_hints": {"questions": []},
                "metadata": {"requirements_review_required": "true"},
            }
        ),
        encoding="utf-8",
    )
    confirmed_path.write_text(
        json.dumps(
            {
                "schema_version": "confirmed_requirement_plan_v1",
                "approval_status": "approved",
                "review": {
                    "proposed_parameters": [
                        {
                            "field_path": "source.particle_mixture",
                            "proposed_value": (
                                "中子+gamma混合场（例如14.1 MeV中子 "
                                "+ 2.5 MeV gamma）"
                            ),
                            "source_type": "user_confirmed",
                        },
                        {
                            "field_path": "source.position_direction",
                            "proposed_value": (
                                "从机器人正上方1米处，沿-Z方向垂直入射的"
                                "平行束，束半径5 cm"
                            ),
                            "source_type": "user_confirmed",
                        },
                        {
                            "field_path": "run.event_count",
                            "proposed_value": "100000",
                            "source_type": "user_confirmed",
                        },
                        {
                            "field_path": "scoring.objective",
                            "proposed_value": "机器人体内各层的能量沉积（MeV）和吸收剂量（Gy）",
                            "source_type": "user_confirmed",
                        },
                        {
                            "field_path": "physics_list",
                            "proposed_value": (
                                "QGSP_BIC_HP（适用于中子-质子输运）或 "
                                "QGSP_BERT（适用于gamma主导）"
                            ),
                            "source_type": "user_confirmed",
                        },
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await load_task_spec(
        {
            "task_spec_path": str(task_spec_path),
            "confirmed_requirement_plan_path": str(confirmed_path),
        }
    )

    task_spec = result["task_spec"]
    assert "particle" not in task_spec
    assert task_spec["events"] == 100000
    assert task_spec["outputs"] == ["energy_deposition", "dose_distribution", "event_data"]
    assert task_spec["physics_options"]["physics_list"] == "QGSP_BIC_HP"
    assert [particle["type"] for particle in task_spec["particles"]] == ["neutron", "gamma"]
    assert [particle["energy_MeV"] for particle in task_spec["particles"]] == [14.1, 2.5]
    assert task_spec["particles"][0]["direction"] == [0.0, 0.0, -1.0]
    assert task_spec["particles"][0]["position"] == [0.0, 0.0, 1000000.0]
    assert task_spec["particles"][0]["surface_shape"] == "circle"
    assert task_spec["particles"][0]["surface_size"] == [50000.0]


async def test_g4_modeling_does_not_upgrade_single_particle_optional_text_to_mixture(
    tmp_path,
) -> None:
    """Optional alternatives in a single source answer are not confirmed sources."""
    from agent_core.g4_modeling.subgraph_io import load_task_spec

    task_spec_path = tmp_path / "task_spec.json"
    confirmed_path = tmp_path / "confirmed_requirement_plan.json"
    task_spec_path.write_text(
        json.dumps({"simulation_scope": ["geant4"], "particle": {}}),
        encoding="utf-8",
    )
    confirmed_path.write_text(
        json.dumps(
            {
                "schema_version": "confirmed_requirement_plan_v1",
                "approval_status": "approved",
                "review": {
                    "proposed_parameters": [
                        {
                            "field_path": "source.particle",
                            "proposed_value": (
                                "gamma（若需更真实可选中子+gamma混合场，如"
                                "14.1 MeV中子 + 2.5 MeV gamma）"
                            ),
                        },
                        {
                            "field_path": "source.energy",
                            "proposed_value": "10 MeV 单能",
                        },
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = await load_task_spec(
        {
            "task_spec_path": str(task_spec_path),
            "confirmed_requirement_plan_path": str(confirmed_path),
        }
    )

    particles = result["task_spec"]["particles"]
    assert len(particles) == 1
    assert particles[0]["type"] == "gamma"
    assert particles[0]["energy_MeV"] == 10.0


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
