from __future__ import annotations

from agent_core.intent.schemas import IntentResult


def fallback_intent(
    user_query: str,
    *,
    reason: str = "",
) -> IntentResult:
    """Fallback when the LM cannot classify.

    Explicit simulation requests still enter RadAgent's only executable
    pipeline, which is Geant4. Ambiguous short commands stay in chat so they do
    not create a new job without an active-job decision.
    """
    if _looks_like_explicit_simulation_request(user_query):
        return IntentResult(
            intent="simulation_work",
            confidence=0.0,
            routing_reason=(
                "LM intent classification unavailable; explicit simulation "
                f"request routed to Geant4 pipeline. {reason}"
            ),
            normalized_user_query=user_query.strip(),
            intent_detail="simulation_request",
            requires_job=True,
            requires_simulation_pipeline=True,
        )
    return IntentResult(
        intent="chat",
        confidence=0.0,
        routing_reason=f"LM intent classification unavailable; defaulting to chat. {reason}",
        normalized_user_query=user_query.strip(),
        intent_detail="unknown",
        requires_job=False,
        requires_simulation_pipeline=False,
    )


def _looks_like_explicit_simulation_request(user_query: str) -> bool:
    text = user_query.strip().lower()
    if not text:
        return False
    explicit_markers = (
        "geant4",
        "g4",
        "仿真",
        "模拟",
        "辐照",
        "粒子输运",
        "蒙特卡罗",
        "simulation",
        "simulate",
        "irradiation",
        "monte carlo",
    )
    if not any(marker in text for marker in explicit_markers):
        return False
    non_task_questions = (
        "怎么用",
        "如何使用",
        "what can",
        "how to use",
        "help",
        "帮助",
    )
    return not any(marker in text for marker in non_task_questions)
