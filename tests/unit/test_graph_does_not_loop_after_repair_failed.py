"""P0-15: Graph does not loop after repair fails."""

from __future__ import annotations

from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_repair


def test_repaired_routes_to_hard_gate():
    route_fn = _route_after_repair("material")
    state = {
        "module_repair_results": {
            "material": {"status": "repaired", "attempts": 1},
        },
    }
    assert route_fn(state) == "material_hard_gate"


def test_failed_routes_to_persist():
    route_fn = _route_after_repair("material")
    state = {
        "module_repair_results": {
            "material": {"status": "failed", "attempts": 3},
        },
    }
    assert route_fn(state) == "material_complete"


def test_failed_does_not_route_to_next_module():
    """P0-15: Failed repair must NOT go to the next module branch."""
    route_fn = _route_after_repair("material")
    state = {
        "module_repair_results": {
            "material": {"status": "failed", "attempts": 3},
        },
    }
    result = route_fn(state)
    assert result != "run_geometry_agent"
    assert result == "material_complete"


def test_missing_repair_result_routes_to_hard_gate():
    """No repair result yet — assume repaired (shouldn't happen)."""
    route_fn = _route_after_repair("material")
    state = {"module_repair_results": {}}
    assert route_fn(state) == "material_hard_gate"
