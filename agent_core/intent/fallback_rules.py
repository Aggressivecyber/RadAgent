from __future__ import annotations

from agent_core.intent.schemas import IntentResult


def fallback_intent(
    user_query: str,
    *,
    reason: str = "",
) -> IntentResult:
    """Conservative fallback when the LM cannot classify.

    Do not infer simulation work from keywords here. If the classifier cannot
    get a valid LM decision, keep the user in chat instead of starting a
    simulation pipeline from a rule-based guess.
    """
    return IntentResult(
        intent="chat",
        confidence=0.0,
        routing_reason=f"LM intent classification unavailable; defaulting to chat. {reason}",
        normalized_user_query=user_query.strip(),
        intent_detail="unknown",
        requires_job=False,
        requires_simulation_pipeline=False,
    )
