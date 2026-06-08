"""E2E test — pipeline blocks when no human response is provided.

Verifies that when human confirmation is required but no raw_human_response
is provided, the pipeline correctly:
1. Sets confirmation_status to "pending" (not "approved")
2. Routes back to human_confirmation_subgraph (NOT to codegen)
3. Does NOT proceed to codegen without explicit user approval
4. Triple guard in route_after_human_confirmation catches missing paths

This is a critical safety test: the pipeline must never auto-approve.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_core.graph.main_routes import route_after_human_confirmation

# ─── Test: human_interrupt_node returns pending when no response ────────


class TestPipelineBlocksWithoutHumanResponse:
    """Verify pipeline blocks when no human response is provided."""

    @pytest.mark.asyncio
    async def test_interrupt_node_returns_pending_without_response(self, tmp_path: Path) -> None:
        """human_interrupt_node must return 'pending' when no raw_human_response."""
        from agent_core.human_confirmation.nodes import human_interrupt_node

        state = {
            "job_id": "block-test-001",
            "confirmation_status": "",
            "raw_human_response": None,  # No response provided
        }
        result = await human_interrupt_node(state)
        assert result["confirmation_status"] == "pending"
        assert result.get("user_decision") is None

    @pytest.mark.asyncio
    async def test_interrupt_node_returns_pending_with_empty_dict(self, tmp_path: Path) -> None:
        """human_interrupt_node must return 'pending' when raw_human_response is empty dict."""
        from agent_core.human_confirmation.nodes import human_interrupt_node

        state = {
            "job_id": "block-test-002",
            "confirmation_status": "",
            "raw_human_response": {},  # Empty dict = no response
        }
        result = await human_interrupt_node(state)
        assert result["confirmation_status"] == "pending"

    @pytest.mark.asyncio
    async def test_interrupt_node_returns_received_with_explicit_response(
        self, tmp_path: Path
    ) -> None:
        """human_interrupt_node must return 'received' ONLY when explicit response exists."""
        from agent_core.human_confirmation.nodes import human_interrupt_node

        state = {
            "job_id": "block-test-003",
            "confirmation_status": "",
            "raw_human_response": {
                "schema_version": "confirmation_response_v1",
                "job_id": "block-test-003",
                "round_id": 1,
                "user_decision": "approve",
                "edits": [],
                "user_notes": "Approved",
            },
        }
        result = await human_interrupt_node(state)
        assert result["confirmation_status"] == "received"

    def test_route_pending_goes_back_to_human_confirmation(self) -> None:
        """Route after confirmation: 'pending' → human_confirmation_subgraph (re-entry)."""
        result = route_after_human_confirmation(
            {
                "confirmation_status": "pending",
            }
        )
        assert result == "human_confirmation_subgraph"

    def test_route_no_paths_blocks_codegen(self) -> None:
        """Triple guard: even 'approved' without record/plan paths → report_subgraph."""
        # Missing confirmation_record_path
        result = route_after_human_confirmation(
            {
                "confirmation_status": "approved",
                "confirmed_model_plan_path": "/tmp/plan.json",
                "unconfirmed_assumptions_count": 0,
                # Missing confirmation_record_path
            }
        )
        assert result == "report_subgraph"

        # Missing confirmed_model_plan_path
        result = route_after_human_confirmation(
            {
                "confirmation_status": "approved",
                "confirmation_record_path": "/tmp/record.json",
                "unconfirmed_assumptions_count": 0,
                # Missing confirmed_model_plan_path
            }
        )
        assert result == "report_subgraph"

        # Has unconfirmed assumptions
        result = route_after_human_confirmation(
            {
                "confirmation_status": "approved",
                "confirmation_record_path": "/tmp/record.json",
                "confirmed_model_plan_path": "/tmp/plan.json",
                "unconfirmed_assumptions_count": 3,
            }
        )
        assert result == "report_subgraph"

    def test_route_rejected_goes_to_report(self) -> None:
        """Route after confirmation: 'rejected' → report_subgraph."""
        result = route_after_human_confirmation(
            {
                "confirmation_status": "rejected",
            }
        )
        assert result == "report_subgraph"

    def test_route_failed_goes_to_report(self) -> None:
        """Route after confirmation: 'failed' → report_subgraph."""
        result = route_after_human_confirmation(
            {
                "confirmation_status": "failed",
            }
        )
        assert result == "report_subgraph"

    def test_route_expired_goes_to_report(self) -> None:
        """Route after confirmation: 'expired' → report_subgraph."""
        result = route_after_human_confirmation(
            {
                "confirmation_status": "expired",
            }
        )
        assert result == "report_subgraph"

    def test_route_approved_with_all_guards_goes_to_codegen(self) -> None:
        """Route after confirmation: 'approved' + all guards → codegen."""
        result = route_after_human_confirmation(
            {
                "confirmation_status": "approved",
                "confirmation_record_path": "/tmp/record.json",
                "confirmed_model_plan_path": "/tmp/plan.json",
                "unconfirmed_assumptions_count": 0,
            }
        )
        assert result == "g4_codegen_subgraph"

    def test_route_edited_with_all_guards_goes_to_codegen(self) -> None:
        """Route after confirmation: 'edited' + all guards → codegen."""
        result = route_after_human_confirmation(
            {
                "confirmation_status": "edited",
                "confirmation_record_path": "/tmp/record.json",
                "confirmed_model_plan_path": "/tmp/plan.json",
                "unconfirmed_assumptions_count": 0,
            }
        )
        assert result == "g4_codegen_subgraph"

    def test_route_ask_more_goes_to_context(self) -> None:
        """Route after confirmation: 'ask_more' → context_subgraph."""
        result = route_after_human_confirmation(
            {
                "confirmation_status": "ask_more",
            }
        )
        assert result == "context_subgraph"


# ─── Subgraph-level integration ────────────────────────────────────────


class TestHumanConfirmationSubgraphBlocking:
    """Test human confirmation subgraph blocks without response."""

    @pytest.mark.asyncio
    async def test_subgraph_ends_on_pending(self, tmp_path: Path) -> None:
        """When human_interrupt_node returns pending, the subgraph ends
        (main graph handles re-entry via route_after_human_confirmation)."""
        from agent_core.graph.subgraphs.human_confirmation_graph import (
            _route_after_interrupt,
        )

        # pending → END (subgraph ends, main graph routes back)
        result = _route_after_interrupt({"confirmation_status": "pending"})
        # The END sentinel in LangGraph
        assert result == "__end__"

    @pytest.mark.asyncio
    async def test_subgraph_proceeds_on_received(self, tmp_path: Path) -> None:
        """When human_interrupt_node returns received, subgraph proceeds to parse."""
        from agent_core.graph.subgraphs.human_confirmation_graph import (
            _route_after_interrupt,
        )

        result = _route_after_interrupt({"confirmation_status": "received"})
        assert result == "parse_confirmation_response"
