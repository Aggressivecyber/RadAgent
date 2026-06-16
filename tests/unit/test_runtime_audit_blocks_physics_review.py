"""Runtime execution audit failure blocks physics review and triggers repair."""

from __future__ import annotations

from agent_core.g4_codegen.schemas import G4CodegenSubgraphState
from agent_core.graph.subgraphs.g4_codegen_graph import _route_after_runtime_execution_audit


class TestRuntimeAuditBlocksPhysicsReview:
    """Verify invalid runtime artifacts never route directly to physics review."""

    def test_runtime_audit_fail_routes_to_project_agent_before_budget_exhaustion(self) -> None:
        state: G4CodegenSubgraphState = {
            "runtime_execution_audit": {"status": "fail"},
            "runtime_audit_repair_attempts": 0,
        }

        next_node = _route_after_runtime_execution_audit(state)
        assert next_node == "geant4_project_agent"

    def test_runtime_audit_pass_routes_to_physics_review(self) -> None:
        state: G4CodegenSubgraphState = {
            "runtime_execution_audit": {"status": "pass"},
        }

        next_node = _route_after_runtime_execution_audit(state)
        assert next_node == "physics_quality_review"

    def test_runtime_audit_revise_routes_to_project_agent_before_budget_exhaustion(
        self,
    ) -> None:
        state: G4CodegenSubgraphState = {
            "runtime_execution_audit": {
                "status": "revise",
                "blocking_errors": ["artifact contract not trustworthy"],
            },
            "runtime_audit_repair_attempts": 0,
        }

        next_node = _route_after_runtime_execution_audit(state)
        assert next_node == "geant4_project_agent"

    def test_runtime_audit_failure_routes_to_persist_after_budget_exhaustion(self) -> None:
        state: G4CodegenSubgraphState = {
            "runtime_execution_audit": {"status": "fail"},
            "runtime_audit_repair_attempts": 2,
        }

        next_node = _route_after_runtime_execution_audit(state)
        assert next_node == "persist_codegen_output"

    def test_runtime_audit_budget_exhaustion_requests_continuation(self) -> None:
        from agent_core.g4_codegen.graph_nodes import _audit_failure_continuation_request

        request = _audit_failure_continuation_request(
            {
                "global_integration_agent_report": {
                    "agentic": {"n_turns": 64},
                },
                "runtime_execution_audit": {
                    "status": "fail",
                    "blocking_errors": [
                        "particle_tracks.json has no usable tracks",
                        "energy_deposits.json has no positive deposits",
                    ],
                },
                "runtime_audit_repair_attempts": 2,
            },
            audit_kind="runtime_execution_audit",
        )

        assert request["status"] == "pending"
        assert request["reason"] == "runtime_execution_audit_repair_budget_exhausted"
        assert request["current_turns"] == 64
        assert request["repair_attempts"] == 2
        assert request["requested_total_turns"] > request["current_turns"]
