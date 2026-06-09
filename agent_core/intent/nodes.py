from __future__ import annotations

from typing import Any

from agent_core.intent.router import classify_intent_with_lite_model


async def intent_router_node(state: dict[str, Any]) -> dict[str, Any]:
    user_query = state.get("user_query", "")
    has_active_job = bool(state.get("job_id")) or bool(state.get("job_workspace"))

    intent = await classify_intent_with_lite_model(
        user_query,
        has_active_job=has_active_job,
    )

    return {
        "intent": intent.intent,
        "intent_detail": intent.intent_detail,
        "intent_confidence": intent.confidence,
        "intent_routing_reason": intent.routing_reason,
        "normalized_user_query": intent.normalized_user_query,
        "requires_job": intent.requires_job,
        "requires_simulation_pipeline": intent.requires_simulation_pipeline,
        "requires_clarification": intent.requires_clarification,
        "current_node": "intent_router",
    }
