"""子图节点: 提取用户意图（轨道、材料、层数、粒子类型等）"""

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command

from radagent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.subgraphs.state import ResearchState

try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, temperature=0)
except Exception:
    llm = None

SYSTEM_PROMPT = """你是空天辐照仿真意图提取专家。从用户描述中提取以下信息:

返回 JSON 格式（不要其他内容）:
{
    "orbit": {"name": "轨道名称(LEO/MEO/GEO/HEO/深空)", "altitude_km": 高度数值, "inclination_deg": 倾角},
    "layers": [
        {"name": "层名", "material": "材料", "thickness_mm": 厚度, "role": "shield/insulation/structure/sensitive"}
    ],
    "particles": ["粒子类型列表"],
    "mission": {"duration_years": 任务时长, "purpose": "用途描述"},
    "missing": ["缺失的关键信息列表"]
}

缺失信息填 null。没有提到的字段填 null。只提取用户明确提到的内容。"""

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
              f"layers={len(intent.get('layers', []))} 层, "
              f"particles={intent.get('particles')}, "
              f"missing={intent.get('missing')}")

    update = {"intent_data": intent, "parse_error": ""}
    log_node_exit(_NODE, "design_schema", update)
    return Command(update=update, goto="design_schema")
