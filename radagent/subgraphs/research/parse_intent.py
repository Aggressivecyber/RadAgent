"""子图节点: 提取用户意图（轨道、材料、层数、粒子类型等）"""

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.subgraphs.research.state import ResearchState
from radagent.tools.model_router import get_light_llm

llm = get_light_llm()

SYSTEM_PROMPT = """你是空天辐照仿真意图提取专家。从用户描述中提取以下信息:

返回 JSON 格式（不要其他内容）:
{
    "orbit": {"name": "轨道名称(LEO/MEO/GEO/HEO/深空)", "altitude_km": 高度数值, "inclination_deg": 倾角},
    "layers": [
        {"name": "层名", "material": "材料", "thickness_mm": 厚度, "role": "shield/insulation/structure/sensitive"}
    ],
    "particles": ["粒子类型列表"],
    "scenarios": [
        {"name": "场景名", "particle": "粒子名(中文也行)", "energy_per_nucleon_MeV": 核子能量或null, "energy_MeV": 总能量或null, "num_events": 事件数, "source_type": "parallel_beam/isotropic/hemisphere或null", "energy_spectrum_MeV": [能量列表]或null, "spectrum_probabilities": [概率列表]或null}
    ],
    "mission": {"duration_years": 任务时长, "purpose": "用途描述"},
    "size_xy_cm": 横截面大小或null,
    "missing": ["缺失的关键信息列表"]
}

注意:
- scenarios: 如果用户明确列出了要模拟的场景，逐个提取。重离子能量用 energy_per_nucleon_MeV，普通粒子用 energy_MeV
- source_type: 源类型。平行束默认 parallel_beam，各向同性用 isotropic（深空环境），半球用 hemisphere。用户未指定则填 null
- energy_spectrum_MeV: 如果用户描述了能谱分布（如"10-1000 MeV 能谱"、"宽能谱"），提取能谱能量点列表。单能不填
- spectrum_probabilities: 对应能谱的相对概率权重（如用户描述了 ~1/E 分布则近似填入）。用户未描述概率则填 null
- size_xy_cm: 用户指定的横截面尺寸
- particles 只列粒子类型，详细参数在 scenarios 中
- 缺失信息填 null。只提取用户明确提到的内容。"""

_NODE = "parse_intent"


def _strip_markdown(content: str) -> str:
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return content


def parse_intent(state: ResearchState) -> Command[Literal["parse_intent", "design_schema"]]:
    """提取用户意图关键词"""
    log_node_entry(_NODE, state)

    user_input = state["user_input"]
    parse_error = state.get("parse_error", "")

    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    if parse_error:
        messages.append(HumanMessage(content=f"上次解析失败: {parse_error}\n\n请重新解析: {user_input}"))
        log_info(_NODE, f"重试解析 (上次错误: {parse_error[:100]})")
    else:
        messages.append(HumanMessage(content=user_input))

    response = llm.invoke(messages)
    content = _strip_markdown(response.content.strip())

    log_llm_call(_NODE, user_input, content)

    try:
        intent = json.loads(content)
    except json.JSONDecodeError:
        error_msg = f"意图解析失败: {content[:200]}"
        log_error(_NODE, error_msg)
        update = {"parse_error": error_msg}
        log_node_exit(_NODE, "parse_intent (重试)", update)
        return Command(update=update, goto="parse_intent")

    log_info(_NODE, f"解析结果: orbit={intent.get('orbit')}, "
              f"layers={len(intent.get('layers') or [])} 层, "
              f"particles={intent.get('particles')}, "
              f"scenarios={len(intent.get('scenarios') or [])} 个, "
              f"size_xy_cm={intent.get('size_xy_cm')}, "
              f"missing={intent.get('missing')}")

    update = {"intent_data": intent, "parse_error": ""}
    log_node_exit(_NODE, "design_schema", update)
    return Command(update=update, goto="design_schema")
