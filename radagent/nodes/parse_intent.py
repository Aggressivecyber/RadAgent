"""节点: 解析用户意图，提取结构化仿真参数 (LLM + RAG)"""

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command

from radagent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from radagent.schemas import ControlState, MaterialSpec, ParticleSpec, SimulationParams
from radagent.state import RadAgentState
from radagent.tools.knowledge import lookup_material, lookup_particle, recommend_physics

try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, temperature=0)
except Exception:
    llm = None

SYSTEM_PROMPT = """你是辐照仿真参数提取专家。从用户的自然语言描述中提取仿真参数。

必须返回以下 JSON 格式（不要其他内容）:
{
    "particle": "粒子类型（中文或英文）",
    "energy_MeV": 能量数值（转为MeV），
    "material": "材料名称（中文或英文）",
    "thickness_um": 厚度数值（转为um），
    "num_events": 事件数（默认10000），
    "physics_list": "物理列表（默认auto）"
}

如果信息不完整，用合理默认值填充。energy 支持 keV/MeV/GeV 自动转换。thickness 支持 nm/um/mm/cm 自动转换。"""


def _try_rag_lookup(query: str) -> str:
    """尝试通过 RAG 查找 Geant4 相关知识"""
    try:
        from radagent.rag.search import search_geant4
        results = search_geant4(query, top_k=3)
        if results:
            return "\n".join(f"- {r['title']}: {r['content'][:200]}" for r in results)
    except Exception:
        pass
    return ""


def parse_intent(state: RadAgentState) -> dict:
    """解析用户输入，提取仿真参数"""
    user_input = state["user_input"]
    parse_error = state.get("parse_error", "")

    # 构建消息
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    if parse_error:
        messages.append(HumanMessage(content=f"上次解析失败: {parse_error}\n\n请重新解析: {user_input}"))
    else:
        messages.append(HumanMessage(content=user_input))

    response = llm.invoke(messages)
    content = response.content.strip()

    # 清理 markdown 代码块
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        raw = json.loads(content)
    except json.JSONDecodeError:
        # RAG 辅助: 查找相关知识帮助解析
        rag_context = _try_rag_lookup(user_input)
        if rag_context:
            messages.append(HumanMessage(content=f"参考知识:\n{rag_context}\n\n请重新提取参数。"))
            response = llm.invoke(messages)
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            try:
                raw = json.loads(content)
            except json.JSONDecodeError:
                return {"parse_error": f"无法解析 LLM 输出: {content[:200]}"}
        else:
            return {"parse_error": f"无法解析 LLM 输出: {content[:200]}"}

    # 查找材料和粒子
    g4_material, density = lookup_material(raw.get("material", ""))
    particle = lookup_particle(raw.get("particle", ""))
    physics = recommend_physics(particle, raw.get("energy_MeV", 1.0))

    # 如果用户指定了物理列表
    if raw.get("physics_list", "auto") != "auto":
        physics = raw["physics_list"]

    params = SimulationParams(
        particle=ParticleSpec(
            particle=particle,
            energy_MeV=float(raw.get("energy_MeV", 1.0)),
        ),
        material=MaterialSpec(
            name=raw.get("material", ""),
            geant4_name=g4_material,
            density_g_cm3=density,
            thickness_um=float(raw.get("thickness_um", 100.0)),
        ),
        num_events=int(raw.get("num_events", 10000)),
        physics_list=physics,
    )

    return {"sim_params": params, "parse_error": ""}
