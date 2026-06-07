"""Tests for human_confirmation routing logic."""


from agent_core.graph.main_routes import (
    route_after_g4_modeling,
    route_after_human_confirmation,
)


class TestRouteAfterG4Modeling:
    """Test route_after_g4_modeling function."""

    def test_route_after_g4_modeling_phase1_requires_confirmation(self):
        """Test routing to human_confirmation when required."""
        state = {
            "g4_modeling_status": "passed",
            "human_confirmation_required": True,
        }
        result = route_after_g4_modeling(state)
        assert result == "human_confirmation_subgraph"

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
        }
        result = route_after_human_confirmation(state)
        assert result == "g4_codegen_subgraph"

    def test_route_after_human_confirmation_edited(self):
        """Test routing to codegen after edit."""
        state = {
            "confirmation_status": "edited",
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
        """Test routing back to confirmation for next round."""
        state = {
            "confirmation_status": "pending",
        }
        result = route_after_human_confirmation(state)
        assert result == "human_confirmation_subgraph"

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
