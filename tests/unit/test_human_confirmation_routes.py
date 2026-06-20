"""Tests for human_confirmation routing logic."""

from agent_core.graph.main_routes import (
    route_after_g4_modeling,
    route_after_human_confirmation,
)


class TestRouteAfterG4Modeling:
    """Test route_after_g4_modeling function."""

    def test_route_after_g4_modeling_ignores_legacy_confirmation_flag(self):
        """Requirements review is the only normal confirmation gate before modeling."""
        state = {
            "g4_modeling_status": "passed",
            "human_confirmation_required": True,
        }
        result = route_after_g4_modeling(state)
        assert result == "g4_codegen_subgraph"

    def test_route_after_g4_modeling_no_confirmation(self):
        """Test routing to phase2/codegen when no confirmation needed."""
        state = {
            "g4_modeling_status": "passed",
            "human_confirmation_required": False,
        }
        result = route_after_g4_modeling(state)
        assert result == "g4_codegen_subgraph"

    def test_route_after_g4_modeling_failed(self):
        """Test routing to report when modeling failed."""
        state = {
            "g4_modeling_status": "failed",
            "human_confirmation_required": True,
        }
        result = route_after_g4_modeling(state)
        assert result == "report_subgraph"

    def test_route_after_g4_modeling_needs_user_input(self):
        """Test routing to report when user input needed."""
        state = {
            "g4_modeling_status": "needs_user_input",
            "human_confirmation_required": False,
        }
        result = route_after_g4_modeling(state)
        assert result == "report_subgraph"


class TestRouteAfterHumanConfirmation:
    """Test route_after_human_confirmation function."""

    def test_route_after_human_confirmation_approved(self):
        """Test routing to codegen after approval."""
        state = {
            "confirmation_status": "approved",
            "unconfirmed_assumptions_count": 0,
            "confirmation_record_path": "x/confirmation_record.json",
            "confirmed_model_plan_path": "x/confirmed_model_plan.json",
        }
        result = route_after_human_confirmation(state)
        assert result == "g4_codegen_subgraph"

    def test_route_after_human_confirmation_edited(self):
        """Test routing to codegen after edit."""
        state = {
            "confirmation_status": "edited",
            "unconfirmed_assumptions_count": 0,
            "confirmation_record_path": "x/confirmation_record.json",
            "confirmed_model_plan_path": "x/confirmed_model_plan.json",
        }
        result = route_after_human_confirmation(state)
        assert result == "g4_codegen_subgraph"

    def test_route_after_human_confirmation_rejected(self):
        """Test routing to report after rejection."""
        state = {
            "confirmation_status": "rejected",
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"

    def test_route_after_human_confirmation_ask_more(self):
        """Test routing to context for more information."""
        state = {
            "confirmation_status": "ask_more",
        }
        result = route_after_human_confirmation(state)
        assert result == "context_subgraph"

    def test_route_after_human_confirmation_failed(self):
        """Test routing to report after failed validation."""
        state = {
            "confirmation_status": "failed",
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"

    def test_route_after_human_confirmation_pending(self):
        """Test routing to report when one-shot graph is pending user input."""
        state = {
            "confirmation_status": "pending",
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"

    def test_route_after_human_confirmation_expired(self):
        """Test routing to report after confirmation expired."""
        state = {
            "confirmation_status": "expired",
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"

    def test_route_after_human_confirmation_unknown_status(self):
        """Test routing to report for unknown status."""
        state = {
            "confirmation_status": "unknown_status",
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"


class TestRouteAfterHumanConfirmationBlocking:
    """Test that incomplete confirmations block codegen."""

    def test_approved_without_record_blocks_codegen(self):
        """Test that missing confirmation_record blocks codegen."""
        state = {
            "confirmation_status": "approved",
            "confirmed_model_plan_path": "x/confirmed_model_plan.json",
            "unconfirmed_assumptions_count": 0,
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"

    def test_approved_without_plan_blocks_codegen(self):
        """Test that missing confirmed_model_plan blocks codegen."""
        state = {
            "confirmation_status": "approved",
            "confirmation_record_path": "x/confirmation_record.json",
            "unconfirmed_assumptions_count": 0,
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"

    def test_unconfirmed_assumptions_blocks_codegen(self):
        """Test that unconfirmed assumptions block codegen."""
        state = {
            "confirmation_status": "approved",
            "confirmation_record_path": "x/confirmation_record.json",
            "confirmed_model_plan_path": "x/confirmed_model_plan.json",
            "unconfirmed_assumptions_count": 1,
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"

    def test_edited_without_record_blocks_codegen(self):
        """Test that edited status without record blocks codegen."""
        state = {
            "confirmation_status": "edited",
            "confirmed_model_plan_path": "x/confirmed_model_plan.json",
            "unconfirmed_assumptions_count": 0,
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"

    def test_approved_with_record_and_plan_goes_to_codegen(self):
        """Test that complete approval proceeds to codegen."""
        state = {
            "confirmation_status": "approved",
            "confirmation_record_path": "x/confirmation_record.json",
            "confirmed_model_plan_path": "x/confirmed_model_plan.json",
            "unconfirmed_assumptions_count": 0,
        }
        result = route_after_human_confirmation(state)
        assert result == "g4_codegen_subgraph"

    def test_modeling_failure_blocks_codegen_after_approval(self):
        """Test that approval cannot bypass a failed modeling phase."""
        state = {
            "g4_modeling_status": "failed",
            "confirmation_status": "approved",
            "confirmation_record_path": "x/confirmation_record.json",
            "confirmed_model_plan_path": "x/confirmed_model_plan.json",
            "unconfirmed_assumptions_count": 0,
        }
        result = route_after_human_confirmation(state)
        assert result == "report_subgraph"


class TestRouteAfterG4ModelingPhase2:
    """Test routing for G4 Modeling Phase 2 scenarios.

    Note: These tests verify the routing behavior for Phase 2
    (post-confirmation). The actual route_after_g4_modeling
    function doesn't distinguish phases; it routes based on
    g4_modeling_status and human_confirmation_required.
    """

    def test_route_after_g4_modeling_phase2_passed(self):
        """Test routing to codegen after phase2 passes."""
        state = {
            "g4_modeling_status": "passed",
            "human_confirmation_required": False,
        }
        result = route_after_g4_modeling(state)
        assert result == "g4_codegen_subgraph"

    def test_route_after_g4_modeling_phase2_failed(self):
        """Test routing to report after phase2 fails."""
        state = {
            "g4_modeling_status": "failed",
            "human_confirmation_required": False,
        }
        result = route_after_g4_modeling(state)
        assert result == "report_subgraph"
