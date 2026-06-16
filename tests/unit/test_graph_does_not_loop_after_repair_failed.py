"""P0-15: Graph does not continue after layer completion fails."""

from __future__ import annotations

from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_layer_gate


def test_passed_layer_routes_to_next_node():
    route_fn = _route_after_layer_gate("core_modules_gate", "run_runtime_modules")
    state = {
        "layer_gate_results": {
            "core_modules_gate": {"status": "pass"},
        },
    }
    assert route_fn(state) == "run_runtime_modules"


def test_failed_layer_without_generated_files_routes_to_persist():
    route_fn = _route_after_layer_gate("core_modules_gate", "run_runtime_modules")
    state = {
        "layer_gate_results": {
            "core_modules_gate": {"status": "fail"},
        },
    }
    assert route_fn(state) == "persist_codegen_output"


def test_failed_layer_with_generated_files_routes_to_persist():
    route_fn = _route_after_layer_gate("core_modules_gate", "run_runtime_modules")
    state = {
        "layer_gate_results": {
            "core_modules_gate": {"status": "fail"},
        },
        "module_results": {
            "simulation_core": {
                "status": "failed",
                "generated_files": [
                    {"path": "src/DetectorConstruction.cc", "new_content": "broken"}
                ],
            }
        },
    }
    assert route_fn(state) == "persist_codegen_output"


def test_failed_layer_does_not_route_to_next_layer():
    """P0-15: Failed layer gate must NOT go to the next module layer."""
    route_fn = _route_after_layer_gate("core_modules_gate", "run_runtime_modules")
    state = {
        "layer_gate_results": {
            "core_modules_gate": {"status": "fail"},
        },
    }
    result = route_fn(state)
    assert result != "run_runtime_modules"
    assert result == "persist_codegen_output"


def test_missing_layer_result_routes_to_persist():
    """No layer result should fail closed."""
    route_fn = _route_after_layer_gate("core_modules_gate", "run_runtime_modules")
    state = {"layer_gate_results": {}}
    assert route_fn(state) == "persist_codegen_output"
