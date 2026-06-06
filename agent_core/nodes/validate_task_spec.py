"""Validate TaskSpec node."""

from __future__ import annotations

from agent_core.graph.state import RadiationAgentState
from agent_core.validators.schema_validator import SchemaValidator


async def validate_task_spec(state: RadiationAgentState) -> dict:
    """Validate the task specification against schema requirements."""
    task_spec = state.get("task_spec", {})
    validator = SchemaValidator()
    is_valid, errors = validator.validate_task_spec(task_spec)

    return {
        "task_spec_errors": [] if is_valid else errors,
        "current_node": "validate_task_spec",
    }
