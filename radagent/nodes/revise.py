"""主图节点: 根据门禁反馈修订，路由到对应生产阶段"""
from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.schemas import ControlState
from radagent.state import RadAgentState
from radagent.tools.model_router import get_standard_llm

llm = get_standard_llm()

logger = logging.getLogger("radagent.node.tools")

_NODE = "revise"

REVISE_PROMPT = """你是航天辐照仿真修订专家。根据门禁评估反馈，分析问题根因并决定修订策略。

用户原始需求（最高优先级）:
{user_input}

门禁来源: {gate_source}

门禁评估结果:
{gate_feedback}

当前仿真计划:
{plan_data}

当前构建/运行结果:
{build_data}

当前报告摘要:
{report_summary}

请分析反馈中的每个问题，给出修订策略（JSON 格式）:
{{
    "root_cause": "根因分析",
    "revision_plan": "修订计划描述",
    "route_to": "目标节点名",
    "feedback_for_target": "给目标节点的具体修订指令"
}}

路由规则:
- 门禁来源为 research_gate:
  - 材料名称问题 → route_to = "research"
  - 结构设计问题 → route_to = "research"
  - 场景/轨道参数问题 → route_to = "research"
- 门禁来源为 sim_gate:
  - 编译错误 → route_to = "parameterize"
  - 运行失败 → route_to = "build_and_run"
  - 结果异常 → route_to = "parameterize"
- 门禁来源为 report_gate:
  - 结构缺失 → route_to = "generate_report"
  - 数据不一致 → route_to = "generate_report"
  - 分析不足 → route_to = "generate_report"
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


def revise(state: RadAgentState) -> Command[Literal["research", "parameterize", "build_and_run", "generate_report"]]:
    """根据门禁反馈分析根因，路由到对应生产节点"""
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

    gate_source = state.get("gate_feedback_source", "unknown")
    gate_feedback = state.get("gate_feedback", "")
    parse_error = state.get("parse_error", "")
    user_input = state.get("user_input", "")
    control = state.get("control", ControlState())

    if not gate_feedback and not parse_error:
        log_info(_NODE, "无反馈信息，默认路由到 research")
        update = {"parse_error": ""}
        log_node_exit(_NODE, "research", update)
        return Command(update=update, goto="research")

    feedback_text = gate_feedback or parse_error

    plan = state.get("sim_plan")
    build = state.get("build")
    report = state.get("report", "")

    plan_data = _safe_serialize(plan) if plan else "null"
    build_data = _safe_serialize(build) if build else "null"
    report_summary = report[:1000] if report else "无"

    prompt = REVISE_PROMPT.format(
        user_input=user_input,
        gate_source=gate_source,
        gate_feedback=feedback_text,
        plan_data=plan_data,
        build_data=build_data,
        report_summary=report_summary,
    )

    response = llm.invoke([HumanMessage(content=prompt)])
    content = _strip_markdown(response.content.strip())
    log_llm_call(_NODE, prompt[:500], content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        log_error(_NODE, f"修订策略解析失败: {content[:200]}")
        route_to = _default_route(gate_source)
        update = {"parse_error": "", "gate_feedback": "", "gate_feedback_source": ""}
        log_node_exit(_NODE, f"{route_to} (降级)", update)
        return Command(update=update, goto=route_to)

    route_to = data.get("route_to", "")
    feedback_for_target = data.get("feedback_for_target", "")
    root_cause = data.get("root_cause", "")
    revision_plan = data.get("revision_plan", "")

    valid_targets = {"research", "parameterize", "build_and_run", "generate_report"}
    if route_to not in valid_targets:
        route_to = _default_route(gate_source)

    revised_fb = f"[REVISE] 根因: {root_cause}\n[REVISE] 修订计划: {revision_plan}"
    if feedback_for_target:
        revised_fb += f"\n[REVISE] 具体指令: {feedback_for_target}"

    log_info(_NODE, f"修订完成: source={gate_source}, route_to={route_to}, "
              f"root_cause={root_cause[:80]}")

    update = {
        "gate_feedback": revised_fb,
        "gate_feedback_source": "",
        "parse_error": "",
        "control": ControlState(
            retry_count=control.retry_count + 1,
            max_retries=control.max_retries,
        ),
    }
    log_node_exit(_NODE, route_to, {"route_to": route_to})
    return Command(update=update, goto=route_to)


def _default_route(gate_source: str) -> str:
    """根据门禁来源返回默认路由"""
    return {
        "research_gate": "research",
        "sim_gate": "parameterize",
        "report_gate": "generate_report",
    }.get(gate_source, "research")
