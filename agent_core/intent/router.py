from __future__ import annotations

from agent_core.intent.fallback_rules import fallback_intent
from agent_core.intent.prompts import INTENT_ROUTER_SYSTEM_PROMPT
from agent_core.intent.schemas import IntentResult
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier


async def classify_intent_with_lite_model(
    user_query: str,
    *,
    has_active_job: bool = False,
) -> IntentResult:
    # Hard command short-circuit
    if user_query.strip().startswith("/"):
        return IntentResult(
            intent="command",
            confidence=1.0,
            routing_reason="Slash command detected.",
            normalized_user_query=user_query.strip(),
            extracted_command=user_query.strip().split()[0],
        )

    gateway = get_model_gateway()

    user_prompt = f"""用户输入：
{user_query}

是否有 active job：{has_active_job}

请按系统要求输出 JSON。"""

    result = await gateway.call(
        task=ModelTask.INTENT_ROUTING,
        tier=ModelTier.LITE,
        system_prompt=INTENT_ROUTER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_format="json",
        temperature=0.0,
        max_tokens=1024,
        metadata={"has_active_job": has_active_job},
    )

    if result.error or not result.parsed_json:
        return fallback_intent(
            user_query,
            has_active_job=has_active_job,
            reason=f"lite model failed: {result.error}",
        )

    try:
        return IntentResult.model_validate(result.parsed_json)
    except Exception as exc:
        return fallback_intent(
            user_query,
            has_active_job=has_active_job,
            reason=f"invalid lite intent json: {exc}",
        )
