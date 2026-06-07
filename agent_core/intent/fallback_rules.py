from __future__ import annotations

from agent_core.intent.schemas import IntentResult


def fallback_intent(
    user_query: str,
    *,
    has_active_job: bool = False,
    reason: str = "",
) -> IntentResult:
    q = user_query.strip()
    q_lower = q.lower()

    if q.startswith("/"):
        return IntentResult(
            intent="command",
            confidence=1.0,
            routing_reason="Fallback slash command.",
            normalized_user_query=q,
        )

    if q_lower in {"你好", "您好", "hello", "hi", "嗨", "你是谁"}:
        return IntentResult(
            intent="smalltalk",
            confidence=0.80,
            routing_reason=f"Fallback smalltalk. {reason}",
            normalized_user_query=q,
        )

    sim_keywords = [
        "geant4", "g4", "辐照", "仿真", "粒子", "剂量",
        "探测器", "能量沉积", "tcad", "spice",
    ]
    if any(k in q_lower for k in sim_keywords):
        return IntentResult(
            intent="simulation_request",
            confidence=0.70,
            routing_reason=f"Fallback simulation keyword. {reason}",
            normalized_user_query=q,
            requires_job=True,
            requires_simulation_pipeline=True,
        )

    return IntentResult(
        intent="unknown",
        confidence=0.40,
        routing_reason=f"Fallback unknown. {reason}",
        normalized_user_query=q,
        requires_clarification=True,
    )
