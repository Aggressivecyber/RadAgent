"""子图节点: 根据 research_qc 反馈修订仿真计划"""
from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.subgraphs.research.state import ResearchState
from radagent.tools.model_router import get_standard_llm

llm = get_standard_llm()

logger = logging.getLogger("radagent.node.tools")

_NODE = "revise"

REVISE_PROMPT = """你是航天辐照仿真修订专家。根据质量检查的反馈，修订仿真计划中的问题。

用户原始需求:
{user_input}

当前仿真计划:
{plan_data}

质量检查反馈:
{gate_feedback}

请分析反馈中的每个问题，给出具体的修订建议（JSON 格式）:
{{
    "revised_fields": {{
        "需要修改的字段路径": "建议修改值"
    }},
    "rationale": "修订理由",
    "route_to": "research_params 或 design_schema 或 parse_intent"
}}

修订策略:
- 如果材料名称无效 → 指出正确材料名（G4_ 前缀）
- 如果物理配置不合理 → 给出合理值
- 如果场景不完整 → 建议补充场景
- 如果是结构设计问题 → route_to = "design_schema"
- 如果是意图理解问题 → route_to = "parse_intent"
- 其他参数问题 → route_to = "research_params"
"""


def _strip_markdown(content: str) -> str:
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return content


def _safe_serialize(obj) -> str:
    if obj is None:
        return "null"
    if hasattr(obj, "__dataclass_fields__"):
        fields = {}
        for k in obj.__dataclass_fields__:
            fields[k] = _to_json_safe(getattr(obj, k))
        return json.dumps(fields, ensure_ascii=False, indent=2)
    if isinstance(obj, (list, tuple)):
        return json.dumps([_to_json_safe(i) for i in obj], ensure_ascii=False, indent=2)
    return str(obj)


def _to_json_safe(obj):
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(i) for i in obj]
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_json_safe(getattr(obj, k)) for k in obj.__dataclass_fields__}
    return str(obj)


def revise(state: ResearchState) -> Command[Literal["parse_intent", "design_schema", "research_params"]]:
    """根据 research_qc 反馈修订仿真计划，然后路由到对应生产节点"""
    log_node_entry(_NODE, state)

    # L2 记忆：查询历史尝试
    sim_id = state.get("simulation_id", "")
    prev_attempts = []
    if sim_id:
        from radagent.memory import MemoryStore
        from radagent.config import MEMORY_DB
        try:
            _mem = MemoryStore(MEMORY_DB)
            prev_attempts = _mem.get_attempts(sim_id)
            _mem.close()
            if prev_attempts:
                log_info(_NODE, f"查询到 {len(prev_attempts)} 条历史尝试记录")
        except Exception as e:
            logger.warning("记忆读取失败: %s", e)

    gate_feedback = state.get("gate_feedback", "")
    plan = state.get("sim_plan")
    user_input = state.get("user_input", "")

    if not gate_feedback:
        log_info(_NODE, "无 gate feedback，直接路由到 research_params")
        update = {"parse_error": ""}
        log_node_exit(_NODE, "research_params", update)
        return Command(update=update, goto="research_params")

    plan_data = _safe_serialize(plan) if plan else "null"

    prompt = REVISE_PROMPT.format(
        user_input=user_input,
        plan_data=plan_data,
        gate_feedback=gate_feedback,
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    content = _strip_markdown(response.content.strip())
    log_llm_call(_NODE, prompt[:500], content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        log_error(_NODE, f"修订解析失败: {content[:200]}")
        update = {"parse_error": "", "gate_feedback": ""}
        log_node_exit(_NODE, "research_params (降级)", update)
        return Command(update=update, goto="research_params")

    rationale = data.get("rationale", "")
    route_to = data.get("route_to", "research_params")
    revised_fields = data.get("revised_fields", {})

    if route_to not in ("parse_intent", "design_schema", "research_params"):
        route_to = "research_params"

    revised_fb = gate_feedback
    if rationale:
        revised_fb += f"\n[REVISE_RATIONALE] {rationale}"
    if revised_fields:
        revised_fb += f"\n[REVISE_FIELDS] {json.dumps(revised_fields, ensure_ascii=False)}"

    log_info(_NODE, f"修订完成: route_to={route_to}, rationale={rationale[:100]}")

    update = {
        "gate_feedback": revised_fb,
        "parse_error": "",
        "qc_retry_count": 0,
    }
    log_node_exit(_NODE, route_to, update)
    return Command(update=update, goto=route_to)
