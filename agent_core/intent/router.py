from __future__ import annotations

from typing import Any

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
            reason=f"lite model failed: {result.error}",
        )

    try:
        normalized = _normalize_intent_payload(
            result.parsed_json,
            user_query=user_query,
            has_active_job=has_active_job,
        )
        return IntentResult.model_validate(normalized)
    except Exception as exc:
        return fallback_intent(
            user_query,
            reason=f"invalid lite intent json: {exc}",
        )


def _normalize_intent_payload(
    payload: dict[str, Any],
    *,
    user_query: str,
    has_active_job: bool,
) -> dict[str, Any]:
    data = dict(payload)
    raw_intent = str(data.get("intent", "")).strip()
    raw_detail = str(data.get("intent_detail") or data.get("subintent") or "").strip()

    chat_details = {
        "smalltalk",
        "help",
        "status_query",
        "capability_query",
        "artifact_query",
        "command",
        "unknown",
        "general_question",
    }
    simulation_details = {
        "simulation_request",
        "simulation_edit",
        "simulation_continue",
        "human_confirmation_response",
    }

    if raw_intent in {"chat", "simulation_work"}:
        top_level = raw_intent
        detail = raw_detail or _default_detail_for_top_level(raw_intent)
    elif raw_intent in chat_details:
        top_level = "chat"
        detail = raw_detail or raw_intent
    elif raw_intent in simulation_details:
        top_level = "simulation_work"
        detail = raw_detail or raw_intent
    else:
        fallback = fallback_intent(
            user_query,
            reason=f"unrecognized lite intent: {raw_intent}",
        )
        return fallback.model_dump()

    data["intent"] = top_level
    data["intent_detail"] = detail
    data.setdefault("normalized_user_query", user_query.strip())
    data.setdefault("routing_reason", "Normalized lite intent output.")
    data.setdefault("confidence", 0.5)

    if top_level == "chat" and _looks_like_simulation_task_description(user_query):
        top_level = "simulation_work"
        detail = "simulation_request"
        data["intent"] = top_level
        data["intent_detail"] = detail
        data["routing_reason"] = (
            f"{data.get('routing_reason', 'Normalized lite intent output.')} "
            "Corrected descriptive physics task to simulation_work because it includes "
            "a simulation object/source and observable objective."
        )

    if top_level == "chat":
        data["requires_simulation_pipeline"] = False
        data["requires_job"] = bool(data.get("requires_job", False))
    else:
        data["requires_job"] = True
        data["requires_simulation_pipeline"] = True

    return data


def _default_detail_for_top_level(intent: str) -> str:
    if intent == "simulation_work":
        return "simulation_request"
    return "general_question"


def _looks_like_simulation_task_description(user_query: str) -> bool:
    text = user_query.strip().lower()
    if not text:
        return False
    question_markers = (
        "?",
        "？",
        "为什么",
        "如何",
        "怎么",
        "解释",
        "说明",
        "what",
        "why",
        "how",
        "explain",
    )
    if any(marker in text for marker in question_markers):
        return False

    simulation_entities = (
        "geant4",
        "仿真",
        "模拟",
        "粒子",
        "质子",
        "电子",
        "中子",
        "gamma",
        "proton",
        "electron",
        "neutron",
        "beam",
        "束",
        "源",
        "探测器",
        "detector",
        "器件",
        "硅",
        "silicon",
        "氧化层",
        "oxide",
    )
    task_objectives = (
        "观察",
        "计算",
        "评估",
        "得到",
        "输出",
        "分析",
        "传播",
        "入射",
        "穿过",
        "进入",
        "能量沉积",
        "沉积能量",
        "剂量",
        "轨迹",
        "响应",
        "observe",
        "calculate",
        "evaluate",
        "propagation",
        "incident",
        "deposit",
        "energy deposition",
        "dose",
        "trajectory",
        "response",
    )
    return any(term in text for term in simulation_entities) and any(
        term in text for term in task_objectives
    )
