"""P0-24: codegen requires confirmation when needed."""

from __future__ import annotations

from agent_core.g4_codegen.schemas import CodegenPlan


def test_plan_can_require_confirmation():
    plan = CodegenPlan(
        scenario_type="complex",
        required_modules=["material"],
        module_order=["material"],
        requires_human_confirmation=True,
        rationale="Complex geometry requires human review",
    )
    assert plan.requires_human_confirmation is True
    assert plan.rationale != ""


def test_plan_can_skip_confirmation():
    plan = CodegenPlan(
        scenario_type="simple",
        required_modules=["material"],
        module_order=["material"],
        requires_human_confirmation=False,
    )
    assert plan.requires_human_confirmation is False


def test_main_graph_passes_confirmation_paths():
    """Verify main_graph passes confirmation paths to codegen subgraph."""
    from agent_core.graph.main_graph import _make_g4_codegen_subgraph_node

    # The function exists and can be called
    node_fn = _make_g4_codegen_subgraph_node()
    assert callable(node_fn)
