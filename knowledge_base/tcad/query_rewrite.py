#!/usr/bin/env python3
"""
TCAD 查询改写模块
- 将用户自然语言问题改写为适合向量检索的查询
- 提取 TCAD 关键词（SDE, SProcess, SDevice, Physics section 名等）
- 扩展同义词（如 "radiation damage" → "trap charge, TID, total ionizing dose"）
- 多查询生成（一个用户问题 → 3个不同角度的检索查询）
"""

import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_base.llm_client import call_llm

# ============================================================================
# TCAD 同义词和术语映射
# ============================================================================

# 核心同义词扩展表（用于在 LLM 调用失败时的降级方案）
TCAD_SYNONYMS = {
    # 辐射效应
    "radiation": ["radiation damage", "TID", "total ionizing dose", "trap",
                  "oxide trap", "interface trap", "displacement damage"],
    "辐照": ["radiation", "TID", "total ionizing dose", "trap", "辐射"],
    # 器件结构
    "FinFET": ["finfet", "fin field effect transistor", "multi-gate",
               "3D transistor", "trigate", "double-gate"],
    "MOSFET": ["mosfet", "metal oxide semiconductor", "FET"],
    "NMOS": ["nmos", "n-type mosfet", "n-channel"],
    "PMOS": ["pmos", "p-type mosfet", "p-channel"],
    "CMOS": ["cmos", "complementary mos", "inverter"],
    "BJT": ["bipolar", "bipolar junction transistor"],
    # 仿真工具
    "SDE": ["Sentaurus Structure Editor", "SDE", "geometry editor"],
    "SProcess": ["Sentaurus Process", "SProcess", "process simulation"],
    "SDevice": ["Sentaurus Device", "SDevice", "device simulation"],
    "SVisual": ["Sentaurus Visual", "SVisual", "visualization"],
    # 工艺步骤
    "ion implantation": ["ion implant", "implantation", "doping", "注入"],
    "diffusion": ["thermal diffusion", "annealing", "扩散"],
    "oxidation": ["thermal oxidation", "oxide growth", "氧化"],
    "etching": ["etch", "dry etch", "wet etch", "刻蚀"],
    "deposition": ["deposit", "CVD", "PVD", "ALD", "沉积"],
    # 仿真设置
    "mesh": ["mesh", "grid", "refinement", "meshing", "网格"],
    "physics": ["physical model", "physics model", "物理模型"],
    "contact": ["electrode", "contact", "boundary", "边界"],
    "bias": ["voltage", "bias", "sweep", "偏置"],
    # 物理模型
    "recombination": ["SRH", "Auger", "radiative", "recombination", "复合"],
    "mobility": ["carrier mobility", "DopingDep", "HighFieldSaturation"],
    "bandgap": ["band gap", "bandgap narrowing", "禁带"],
    "breakdown": ["avalanche", "breakdown", "impact ionization", "击穿"],
}


# ============================================================================
# 查询改写提示词
# ============================================================================

REWRITE_SYSTEM = """你是 TCAD Sentaurus 半导体仿真领域的检索专家。
你擅长将用户的自然语言问题改写为精确的技术检索词。"""

REWRITE_PROMPT = """请将用户的查询改写为 3 个适合语义检索的英文查询。

改写要求：
1. 提取 TCAD 关键词（工具名如 SDE/SProcess/SDevice，命令名，Physics section 名等）
2. 扩展同义词（如 "辐射" → "TID, oxide trap, interface trap, radiation damage"）
3. 从 3 个不同角度生成：
   - 工具/命令角度：如何在 Sentaurus 中实现
   - 物理模型角度：涉及哪些物理机制和模型
   - 应用场景角度：实际工程中的用途和案例
4. 每个查询占一行，不要编号，不要解释

用户查询：{query}

改写查询："""


def expand_synonyms(query: str) -> str:
    """基于同义词表扩展查询，返回增强版查询文本"""
    extra_terms = []
    query_lower = query.lower()
    for key, synonyms in TCAD_SYNONYMS.items():
        if key.lower() in query_lower:
            # 只添加前 3 个最相关的同义词
            extra_terms.extend(synonyms[:3])
    if extra_terms:
        # 去重
        extra_terms = list(dict.fromkeys(extra_terms))[:6]
        return query + " | related: " + ", ".join(extra_terms)
    return query


def rewrite_query(query: str) -> list[str]:
    """
    将用户查询改写为多个检索查询。

    返回: [原始查询, 改写1, 改写2, 改写3]
    """
    # 先做同义词扩展
    expanded = expand_synonyms(query)

    # 使用 LLM 生成 3 个改写查询
    prompt = REWRITE_PROMPT.format(query=expanded)
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM},
        {"role": "user", "content": prompt}
    ]

    try:
        response = call_llm(messages, temperature=0.5, max_tokens=512)
        # 按行解析，每行一个查询
        queries = []
        for line in response.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            # 去除可能的编号前缀 (1. 2. 3. 或 1) 2) 3))
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            # 去除引号
            line = line.strip('"\'""''')
            if line:
                queries.append(line)
    except Exception as e:
        print(f"  [WARN] 查询改写 LLM 失败，使用降级方案: {e}", file=sys.stderr)
        queries = _fallback_rewrite(expanded)

    # 组装结果：原始查询 + 最多 3 个改写查询
    result = [query]
    result.extend(queries[:3])
    return result


def _fallback_rewrite(query: str) -> list[str]:
    """LLM 不可用时的降级改写方案：基于关键词规则"""
    queries = []

    # 英文翻译（简单替换中文关键词）
    cn_to_en = {
        "如何": "how to", "设置": "setup configure", "辐照": "radiation TID trap",
        "仿真": "simulation", "网格": "mesh refinement", "物理模型": "physics model",
        "结构": "structure geometry", "工艺": "process", "器件": "device",
        "生成": "generate create", "定义": "define", "参数": "parameter",
        "陷阱": "trap", "模型": "model", "温度": "temperature",
    }
    en_query = query
    for cn, en in cn_to_en.items():
        en_query = en_query.replace(cn, en)

    if en_query != query:
        queries.append(en_query)

    # 添加 TCAD 工具前缀的变体
    tools = ["SDevice", "SProcess", "SDE"]
    for tool in tools:
        if tool.lower() not in query.lower():
            queries.append(f"{tool} {query}")
            break  # 只添加一个工具变体

    # 添加物理模型关键词
    physics_terms = ["physics section", "model", "mesh"]
    for term in physics_terms:
        if term not in query.lower():
            queries.append(f"{query} {term}")
            break

    return queries[:3]


def extract_keywords(query: str) -> list[str]:
    """从查询中提取 TCAD 领域关键词"""
    tcad_terms = [
        # 工具
        "SDE", "SProcess", "SDevice", "SVisual", "SWorkbench",
        "Sentaurus Structure Editor", "Sentaurus Process", "Sentaurus Device",
        # 物理模型
        "mesh", "refinement", "physics", "contact", "boundary",
        "recombination", "mobility", "bandgap", "breakdown", "avalanche",
        # 工艺
        "ion implantation", "diffusion", "oxidation", "etching", "deposition",
        "annealing", "CMP", "lithography",
        # 器件
        "FinFET", "MOSFET", "NMOS", "PMOS", "CMOS", "BJT", "IGBT", "SOI",
        "diode", "resistor", "capacitor",
        # 仿真
        "electric field", "carrier", "generation", "trap",
        "oxide trap", "interface trap", "radiation", "TID",
        "voltage", "current", "IV", "CV", "bias", "sweep",
        # 材料
        "silicon", "SiO2", "SiGe", "GaN", "SiC", "oxide",
    ]

    found = []
    query_lower = query.lower()
    # 先匹配长词，避免短词覆盖长词
    sorted_terms = sorted(tcad_terms, key=len, reverse=True)
    for term in sorted_terms:
        if term.lower() in query_lower:
            found.append(term)
            # 从查询中移除已匹配的词，避免重复
            query_lower = query_lower.replace(term.lower(), "", 1)
    return found


# ============================================================================
# 命令行测试
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    else:
        test_query = "如何设置 NMOS 辐照陷阱模型"

    print(f"原始查询: {test_query}")
    print(f"提取关键词: {extract_keywords(test_query)}")
    print(f"同义词扩展: {expand_synonyms(test_query)}")
    print()

    queries = rewrite_query(test_query)
    print(f"改写查询 ({len(queries)} 个):")
    for i, q in enumerate(queries):
        print(f"  [{i}] {q}")
