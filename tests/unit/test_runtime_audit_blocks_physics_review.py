"""Runtime execution audit failure blocks physics quality review."""

from __future__ import annotations

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState
from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_runtime_execution_audit


class TestRuntimeAuditBlocksPhysicsReview:
    """Verify invalid runtime artifacts route to persist instead of physics review."""

    def test_runtime_audit_fail_routes_to_persist(self) -> None:
        state: G4CodegenSubgraphState = {
            "runtime_execution_audit": {"status": "fail"},
        }

        next_node = _route_after_runtime_execution_audit(state)
        assert next_node == "persist_codegen_output"

    def test_runtime_audit_pass_routes_to_physics_review(self) -> None:
        state: G4CodegenSubgraphState = {
            "runtime_execution_audit": {"status": "pass"},
        }

        next_node = _route_after_runtime_execution_audit(state)
        assert next_node == "physics_quality_review"

    def test_runtime_audit_revise_routes_to_persist(self) -> None:
        state: G4CodegenSubgraphState = {
            "runtime_execution_audit": {
                "status": "revise",
                "blocking_errors": ["artifact contract not trustworthy"],
            },
        }

        next_node = _route_after_runtime_execution_audit(state)
        assert next_node == "persist_codegen_output"
