"""Tests for main graph subgraph routing."""

from __future__ import annotations

from agent_core.graph.main_routes import (
    route_after_artifact,
    route_after_context,
    route_after_g4_codegen,
    route_after_g4_modeling,
    route_after_gates,
    route_after_patch,
    route_after_task_planning,
)
from agent_core.graph.main_state import RadAgentMainState


class TestRouteAfterContext:
    """Tests for route_after_context routing."""

    def test_allow_rag_proceeds(self) -> None:
        state: RadAgentMainState = {"context_decision": "allow_rag"}
        assert route_after_context(state) == "task_planning_subgraph"

    def test_allow_web_supplement_proceeds(self) -> None:
        state: RadAgentMainState = {"context_decision": "allow_with_web_supplement"}
        assert route_after_context(state) == "task_planning_subgraph"

    def test_block_no_context_reports(self) -> None:
        state: RadAgentMainState = {"context_decision": "block_no_context"}
        assert route_after_context(state) == "report_subgraph"

    def test_unknown_defaults_to_report(self) -> None:
        state: RadAgentMainState = {"context_decision": "something_else"}
        assert route_after_context(state) == "report_subgraph"

    def test_empty_defaults_to_report(self) -> None:
        state: RadAgentMainState = {}
        assert route_after_context(state) == "report_subgraph"


class TestRouteAfterTaskPlanning:
    """Tests for route_after_task_planning routing."""

    def test_geant4_scope_proceeds(self) -> None:
        state: RadAgentMainState = {
            "task_planning_status": "passed",
            "simulation_scope": ["geant4"],
        }
        assert route_after_task_planning(state) == "g4_modeling_subgraph"

    def test_failed_status_reports(self) -> None:
        state: RadAgentMainState = {
            "task_planning_status": "failed",
            "simulation_scope": ["geant4"],
        }
        assert route_after_task_planning(state) == "report_subgraph"

    def test_reserved_scope_still_proceeds(self) -> None:
        """TCAD/SPICE reserved scopes still proceed to G4 modeling."""
        state: RadAgentMainState = {
            "task_planning_status": "passed",
            "simulation_scope": ["geant4", "tcad"],
        }
        assert route_after_task_planning(state) == "g4_modeling_subgraph"


class TestRouteAfterG4Modeling:
    """Tests for route_after_g4_modeling routing."""

    def test_passed_proceeds(self) -> None:
        state: RadAgentMainState = {"g4_modeling_status": "passed"}
        assert route_after_g4_modeling(state) == "g4_codegen_subgraph"

    def test_failed_reports(self) -> None:
        state: RadAgentMainState = {"g4_modeling_status": "failed"}
        assert route_after_g4_modeling(state) == "report_subgraph"

    def test_needs_user_input_reports(self) -> None:
        state: RadAgentMainState = {"g4_modeling_status": "needs_user_input"}
        assert route_after_g4_modeling(state) == "report_subgraph"


class TestRouteAfterG4Codegen:
    """Tests for route_after_g4_codegen routing."""

    def test_passed_proceeds(self) -> None:
        state: RadAgentMainState = {"g4_codegen_status": "passed"}
        assert route_after_g4_codegen(state) == "patch_subgraph"

    def test_failed_reports(self) -> None:
        state: RadAgentMainState = {"g4_codegen_status": "failed"}
        assert route_after_g4_codegen(state) == "report_subgraph"


class TestRouteAfterPatch:
    """Tests for route_after_patch routing."""

    def test_applied_proceeds(self) -> None:
        state: RadAgentMainState = {"patch_status": "applied"}
        assert route_after_patch(state) == "gate_subgraph"

    def test_rejected_reports(self) -> None:
        state: RadAgentMainState = {"patch_status": "rejected"}
        assert route_after_patch(state) == "report_subgraph"


class TestRouteAfterGates:
    """Tests for route_after_gates routing."""

    def test_verified_proceeds(self) -> None:
        state: RadAgentMainState = {"validation_status": "VERIFIED"}
        assert route_after_gates(state) == "artifact_subgraph"

    def test_failed_with_retry_context(self) -> None:
        state: RadAgentMainState = {
            "validation_status": "FAILED",
            "retry_count": 0,
            "failed_gates": ["Gate 0"],
        }
        assert route_after_gates(state) == "context_subgraph"

    def test_failed_with_retry_modeling(self) -> None:
        state: RadAgentMainState = {
            "validation_status": "FAILED",
            "retry_count": 0,
            "failed_gates": ["Gate 2"],
        }
        assert route_after_gates(state) == "g4_modeling_subgraph"

    def test_failed_with_retry_codegen(self) -> None:
        state: RadAgentMainState = {
            "validation_status": "FAILED",
            "retry_count": 0,
            "failed_gates": ["Gate 5"],
        }
        assert route_after_gates(state) == "g4_codegen_subgraph"

    def test_failed_max_retries_reports(self) -> None:
        state: RadAgentMainState = {
            "validation_status": "FAILED",
            "retry_count": 5,
            "failed_gates": ["Gate 0"],
        }
        assert route_after_gates(state) == "report_subgraph"

    def test_partial_treated_as_failed(self) -> None:
        state: RadAgentMainState = {
            "validation_status": "PARTIAL",
            "retry_count": 0,
            "failed_gates": ["Gate 5"],
        }
        assert route_after_gates(state) == "g4_codegen_subgraph"


class TestRouteAfterArtifact:
    """Tests for route_after_artifact routing."""

    def test_always_goes_to_report(self) -> None:
        state: RadAgentMainState = {}
        assert route_after_artifact(state) == "report_subgraph"
