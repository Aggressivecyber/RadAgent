"""子图节点: 对 G4 NIST 中未找到的材料/粒子，LLM 生成自定义定义 + C++ 模板代码"""

import json
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from radagent.log import log_node_entry, log_node_exit, log_info, log_error, log_llm_call
from radagent.schemas import ShieldGeometry, ShieldLayer
from radagent.subgraphs.research.state import ResearchState
from radagent.tools.knowledge import (
    register_custom_element,
    register_custom_material,
    register_custom_particle,
    try_lookup_material,
)
from radagent.tools.model_router import get_light_llm

llm = get_light_llm()

_NODE = "define_custom"

DEFINE_PROMPT = """你是材料科学和核物理专家。以下材料/粒子不在 Geant4 NIST 数据库中，需要自定义。

未找到的材料: {materials}
未找到的粒子: {particles}

对于每种材料，请返回其化学组成:
- g4_name: 材料标识名 (如 "G4_SiC")
- density_g_cm3: 室温密度 (g/cm3)
- elements: 元素列表，每项 [Z, 符号, 原子数]，如需特定同位素则加第4项 [Z, 符号, 原子数, A]

对于每种粒子（离子），请返回:
- g4_name: 粒子标识名 (如 "Fe_ion")
- Z: 原子序数
- A: 质量数（如果用户没有指定，采用最丰同位素，否则使用用户指定的值）

对于涉及的同位素（元素列表中含第4项 A 的），请同时在 elements 中注册:
- name: 同位素标识 (如 "Li6")
- Z: 原子序数
- A: 质量数
- symbol: 元素符号

返回 JSON:
{{
  "elements": [
    {{"name": "Li6", "Z": 3, "A": 6, "symbol": "Li"}}
  ],
  "materials": [
    {{"name": "原始名称", "g4_name": "G4_XXX", "density_g_cm3": 3.21, "elements": [[14, "Si", 1], [6, "C", 1]]}}
  ],
  "particles": [
    {{"name": "原始名称", "g4_name": "XXX_ion", "Z": 26, "A": 56}}
  ]
}}
"""


def _strip_markdown(content: str) -> str:
    if content.startswith("```"):
        content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return content


def define_custom(state: ResearchState) -> Command[Literal["research_params"]]:
    """LLM 生成自定义材料/粒子定义，注册到知识库，修正几何"""
    log_node_entry(_NODE, state)

    unresolved_mats = state.get("unresolved_materials", [])
    unresolved_parts = state.get("unresolved_particles", [])

    if not unresolved_mats and not unresolved_parts:
        log_info(_NODE, "无需自定义")
        update = {"unresolved_materials": [], "unresolved_particles": []}
        log_node_exit(_NODE, "research_params", update)
        return Command(update=update, goto="research_params")

    prompt = DEFINE_PROMPT.format(
        materials=json.dumps(unresolved_mats, ensure_ascii=False),
        particles=json.dumps(unresolved_parts, ensure_ascii=False),
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    content = _strip_markdown(response.content.strip())
    log_llm_call(_NODE, prompt, content)

    try:
        defs = json.loads(content)
    except json.JSONDecodeError:
        error_msg = f"自定义定义解析失败: {content[:200]}"
        log_error(_NODE, error_msg)
        update = {"parse_error": error_msg}
        log_node_exit(_NODE, "research_params", update)
        return Command(update=update, goto="research_params")

    # 注册自定义元素（同位素）— 必须在材料之前，材料可能引用它们
    for elem_def in defs.get("elements", []):
        name = elem_def["name"]
        definition = {
            "description": elem_def.get("name", name),
            "Z": int(elem_def["Z"]),
            "A": int(elem_def["A"]),
            "symbol": elem_def["symbol"],
        }
        register_custom_element(name, definition)
        log_info(_NODE, f"注册元素: {name} Z={definition['Z']} A={definition['A']}")

    # 注册自定义材料
    for mat_def in defs.get("materials", []):
        g4_name = mat_def["g4_name"]
        definition = {
            "description": mat_def.get("name", g4_name),
            "type": "compound",
            "density_g_cm3": float(mat_def["density_g_cm3"]),
            "elements": [
                [int(e[0]), e[1], int(e[2])] + ([int(e[3])] if len(e) >= 4 else [])
                for e in mat_def["elements"]
            ],
        }
        register_custom_material(g4_name, definition)
        log_info(_NODE, f"注册材料: {g4_name} ρ={definition['density_g_cm3']}")

    # 注册自定义粒子
    for part_def in defs.get("particles", []):
        g4_name = part_def["g4_name"]
        definition = {
            "description": part_def.get("name", g4_name),
            "type": "ion",
            "Z": int(part_def["Z"]),
            "A": int(part_def["A"]),
        }
        register_custom_particle(g4_name, definition)
        log_info(_NODE, f"注册粒子: {g4_name} Z={definition['Z']} A={definition['A']}")

    # 修正几何中未解析的层
    geometry = state.get("geometry")
    if geometry and unresolved_mats:
        new_layers = []
        for layer in geometry.layers:
            if layer.material in unresolved_mats:
                g4_name, density = try_lookup_material(layer.material)
                new_layers.append(ShieldLayer(
                    name=layer.name,
                    material=layer.material,
                    geant4_material=g4_name or layer.geant4_material,
                    density_g_cm3=density or layer.density_g_cm3,
                    thickness_mm=layer.thickness_mm,
                    role=layer.role,
                ))
                log_info(_NODE, f"修正层: {layer.name} {layer.material} → {g4_name} (ρ={density})")
            else:
                new_layers.append(layer)
        geometry = ShieldGeometry(
            name=geometry.name,
            layers=tuple(new_layers),
            size_xy_cm=geometry.size_xy_cm,
            sensitive_volume=geometry.sensitive_volume,
        )

    update = {
        "geometry": geometry,
        "unresolved_materials": [],
        "unresolved_particles": [],
        "parse_error": "",
    }
    log_node_exit(_NODE, "research_params", update)
    return Command(update=update, goto="research_params")
