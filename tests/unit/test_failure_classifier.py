from agent_core.gates.failure_classifier import (
    classify_failed_gates,
    classify_failure,
    classify_failures_by_gate_names,
)


def test_classify_failure_uses_lowest_gate_priority() -> None:
    assert classify_failure([7, 3]) == "patch_subgraph"


def test_classify_failures_by_gate_names_accepts_descriptive_gate_names() -> None:
    assert classify_failures_by_gate_names(["Gate 5 Static Check"]) == "g4_codegen_subgraph"
    assert classify_failures_by_gate_names(["G4-A Model Completeness"]) == "g4_modeling_subgraph"


def test_classify_failure_routes_task_spec_to_planning() -> None:
    assert classify_failure([1]) == "task_planning_subgraph"


def test_classify_failure_routes_modeling_g4_gates_to_modeling() -> None:
    assert classify_failure([15]) == "g4_modeling_subgraph"
    assert classify_failure([16]) == "g4_modeling_subgraph"


def test_classify_failed_gates_accepts_dicts_and_full_names() -> None:
    assert classify_failed_gates([{"gate_id": 8, "name": "Data Contract"}]) == (
        "g4_codegen_subgraph"
    )
    assert classify_failed_gates(["Task Spec Schema"]) == "task_planning_subgraph"
    assert classify_failed_gates(["G4-H Human Confirmation"]) == "human_confirmation_subgraph"
