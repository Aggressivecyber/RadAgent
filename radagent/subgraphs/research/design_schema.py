"""子图节点: 根据意图设计多层屏蔽几何 + 轨道环境"""

import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command, interrupt

from radagent.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.schemas import OrbitEnvironment, ShieldGeometry, ShieldLayer
from radagent.subgraphs.research.state import ResearchState
from radagent.tools.knowledge import try_lookup_material

try:
    from langchain_openai import ChatOpenAI
    llm = ChatOpenAI(model=DEEPSEEK_MODEL, base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY, temperature=0)
except Exception:
    llm = None

DESIGN_PROMPT = """你是航天器屏蔽结构设计专家。根据用户意图设计多层屏蔽几何。

用户意图: {intent}

请设计多层屏蔽结构（从外到内），返回 JSON:
{{
    "geometry_name": "结构名称",
    "layers": [
        {{"name": "层名", "material": "材料", "thickness_mm": 厚度, "role": "shield/insulation/structure/sensitive"}}
    ],
    "size_xy_cm": 10.0,
    "sensitive_volume": "敏感体积层名",
    "orbit": {{
        "name": "LEO/MEO/GEO/HEO/深空",
        "altitude_km": 高度,
        "inclination_deg": 倾角
    }}
}}

设计原则:
- 根据用户意图合理选择材料和层数，满足屏蔽/绝热/结构/敏感体积的功能需求，如果用户明确提到某些材料、敏感体积或具体层数以及厚度参数请优先使用
- 外层: 结构材料 (铝合金/钛合金)
- 中层: 绝热/屏蔽材料 (聚乙烯/聚酰亚胺)
- 内层: 电子器件/敏感体积 (硅/砷化镓)
- 每层需有合理厚度 (mm)
"""

_NODE = "design_schema"


def _strip_markdown(content: str) -> str:
    """从 LLM 输出中提取 JSON。处理多种 markdown 包裹格式。"""
    import re
    # 情况 1: 以 ``` 开头
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        return content
    # 情况 2: 中间有 ```json ... ``` 包裹
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", content, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 情况 3: 找最外层 { ... }
    first = content.find("{")
    last = content.rfind("}")
    if first >= 0 and last > first:
        return content[first:last + 1]
    return content


# 设计解析最大重试次数（防止无限循环）
_MAX_DESIGN_RETRIES = 3
_retry_count = 0


def design_schema(state: ResearchState) -> Command[Literal["design_schema", "define_custom", "research_params"]]:
    """LLM 设计多层屏蔽几何 + 轨道环境，未找到的材料交由 define_custom 处理"""
    global _retry_count
    log_node_entry(_NODE, state)

    intent = state.get("intent_data", {})
    parse_error = state.get("parse_error", "")

    # 检测重试
    if parse_error and "设计解析失败" in parse_error:
        _retry_count += 1
        if _retry_count > _MAX_DESIGN_RETRIES:
            log_error(_NODE, f"设计解析重试超过 {_MAX_DESIGN_RETRIES} 次，终止")
            _retry_count = 0
            update = {"parse_error": f"设计解析失败 {_MAX_DESIGN_RETRIES} 次，请重新描述需求"}
            log_node_exit(_NODE, "__end__", update)
            return Command(update=update, goto="__end__")
    else:
        _retry_count = 0

    prompt = DESIGN_PROMPT.format(intent=json.dumps(intent, ensure_ascii=False))
    response = llm.invoke([HumanMessage(content=prompt)])
    content = _strip_markdown(response.content.strip())

    log_llm_call(_NODE, prompt, content)

    try:
        design = json.loads(content)
    except json.JSONDecodeError:
        error_msg = f"设计解析失败: {content}"
        log_error(_NODE, error_msg)
        update = {"parse_error": error_msg}
        log_node_exit(_NODE, "design_schema (重试)", update)
        return Command(update=update, goto="design_schema")

    # 构建 ShieldLayer 列表
    layers = []
    unresolved_mats = []
    for layer_data in design.get("layers", []):
        raw_mat = layer_data.get("material", "")
        g4_name, density = try_lookup_material(raw_mat)
        if g4_name is None:
            log_info(_NODE, f"材料未找到: {raw_mat} → 待自定义生成")
            unresolved_mats.append(raw_mat)
        else:
            log_info(_NODE, f"材料查找: {raw_mat} → {g4_name} (ρ={density})")
        layers.append(ShieldLayer(
            name=layer_data.get("name", ""),
            material=raw_mat,
            geant4_material=g4_name or raw_mat,
            density_g_cm3=density if density else 1.0,
            thickness_mm=float(layer_data.get("thickness_mm", 1.0)),
            role=layer_data.get("role", "shield"),
        ))

    if not layers:
        error_msg = "未设计任何屏蔽层，请描述仿真对象"
        log_error(_NODE, error_msg)
        update = {"parse_error": error_msg}
        log_node_exit(_NODE, "design_schema (重试)", update)
        return Command(update=update, goto="design_schema")

    geometry = ShieldGeometry(
        name=design.get("geometry_name", "航天器屏蔽结构"),
        layers=tuple(layers),
        size_xy_cm=float(design.get("size_xy_cm", 10.0)),
        sensitive_volume=design.get("sensitive_volume", ""),
    )

    log_info(_NODE, f"几何设计: {geometry.name}, {len(layers)} 层, "
              f"敏感体积={geometry.sensitive_volume}")
    for l in layers:
        log_info(_NODE, f"  {l.name}: {l.material} ({l.geant4_material}) "
                  f"{l.thickness_mm} mm [{l.role}]")

    # 构建轨道环境
    orbit_data = design.get("orbit", {})
    orbit_name = orbit_data.get("name", "LEO")

    orbit = OrbitEnvironment(
        orbit_name=orbit_name,
        altitude_km=float(orbit_data.get("altitude_km", 500)),
        inclination_deg=float(orbit_data.get("inclination_deg", 0)),
        reference=f"基于 {orbit_name} 轨道参考数据",
    )

    log_info(_NODE, f"轨道: {orbit.orbit_name} ({orbit.altitude_km} km, {orbit.inclination_deg} deg)")

    next_node = "define_custom" if unresolved_mats else "research_params"
    update = {
        "geometry": geometry, "orbit": orbit, "parse_error": "",
        "unresolved_materials": unresolved_mats, "unresolved_particles": [],
    }
    log_node_exit(_NODE, next_node, update)
    return Command(update=update, goto=next_node)
