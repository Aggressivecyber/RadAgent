#!/usr/bin/env python3
"""
ngspice 查询改写模块
- 将用户自然语言问题改写为适合向量检索的查询
- 提取 SPICE 关键词（命令、模型、器件类型等）
- 扩展同义词（如 "MOSFET" → "BSIM, MOS, FET, transistor"）
- 多查询生成（一个用户问题 → 3个不同角度的检索查询）
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error

# 智谱 LLM API 配置
LLM_API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
LLM_API_KEY = "f5dc034a22df47ac8cf98c37710e0bc6.crvx5afiTuITC247"
LLM_MODEL = "glm-5-turbo"

# ============================================================================
# ngspice 同义词和术语映射
# ============================================================================

NGSPICE_SYNONYMS = {
    # 器件类型
    "MOSFET": ["BSIM", "MOS", "FET", "transistor", "nmos", "pmos"],
    "MOS": ["mosfet", "BSIM", "FET", "transistor"],
    "BJT": ["bipolar", "transistor", "npn", "pnp", "Gummel-Poon"],
    "diode": ["diode", "pn junction", "Schottky"],
    "JFET": ["jfet", "junction field effect"],
    " FinFET": ["finfet", "multi-gate", "BSIM-CMG"],
    # 仿真类型
    "DC analysis": ["dc sweep", ".dc", "operating point", ".op", "IV characteristic"],
    "AC analysis": ["ac sweep", ".ac", "frequency response", "Bode"],
    "transient": [".tran", "time domain", "transient analysis", "时域"],
    "transfer function": [".tf", "gain", "impedance", "传输函数"],
    "noise": [".noise", "noise analysis", "thermal noise", "flicker noise"],
    "Monte Carlo": [".mc", "montecarlo", "statistical", "process variation"],
    "pole-zero": [".pz", "poles zeros", "stability"],
    # SPICE 命令
    ".model": ["model card", "device model", "BSIM parameters"],
    ".subckt": ["subcircuit", "macro model", "hierarchical"],
    ".control": ["nutmeg script", "control language", "batch mode"],
    # 模型
    "BSIM": ["BSIM3", "BSIM4", "BSIM-BULK", "BSIM-CMG", "BSIM-SOI"],
    "EKV": ["EKV model", "compact model"],
    "vbic": ["VBIC", "bipolar model"],
    "hicum": ["HICUM", "HICUM2", "bipolar model"],
    # 分析/测量
    "IV curve": ["IV characteristic", "current voltage", "output characteristic"],
    "CV curve": ["CV characteristic", "capacitance voltage"],
    "frequency": ["AC", "Bode plot", "frequency response", "带宽"],
    "simulation": [".tran", ".dc", ".ac", "ngspice simulation", "仿真"],
    # 应用
    "inverter": ["CMOS inverter", "NOT gate", "反相器"],
    "amplifier": ["op amp", "operational amplifier", "common source", "common emitter"],
    "oscillator": ["ring oscillator", "LC oscillator", "crystal oscillator"],
    "filter": ["RC filter", "LC filter", "bandpass", "lowpass", "highpass"],
    "power": ["power amplifier", "DC-DC", "LDO", "voltage regulator"],
}


def call_llm(messages: list, temperature: float = 0.7, max_tokens: int = 2048) -> str:
    """调用智谱 LLM API"""
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }).encode('utf-8')

    req = urllib.request.Request(
        LLM_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
    )

    max_retries = 2
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, IndexError) as e:
            if attempt < max_retries - 1:
                print(f"  [RETRY] LLM 调用失败 (attempt {attempt+1}): {e}", file=sys.stderr)
                time.sleep(2)
            else:
                raise RuntimeError(f"LLM 调用失败: {e}") from e


# ============================================================================
# 查询改写提示词
# ============================================================================

REWRITE_SYSTEM = """你是 ngspice/SPICE 电路仿真领域的检索专家。
你擅长将用户的自然语言问题改写为精确的技术检索词。"""

REWRITE_PROMPT = """请将用户的查询改写为 3 个适合语义检索的英文查询。

改写要求：
1. 提取 SPICE 关键词（命令如 .dc/.ac/.tran，模型如 BSIM/MOSFET，器件类型等）
2. 扩展同义词（如 "反相器" → "CMOS inverter, NOT gate, voltage transfer characteristic"）
3. 从 3 个不同角度生成：
   - 命令/语法角度：如何在 ngspice 中实现
   - 模型/器件角度：涉及哪些器件和模型
   - 应用场景角度：实际电路中的用途和示例
4. 每个查询占一行，不要编号，不要解释

用户查询：{query}

改写查询："""


def expand_synonyms(query: str) -> str:
    """基于同义词表扩展查询"""
    extra_terms = []
    query_lower = query.lower()
    for key, synonyms in NGSPICE_SYNONYMS.items():
        if key.lower() in query_lower:
            extra_terms.extend(synonyms[:3])
    if extra_terms:
        extra_terms = list(dict.fromkeys(extra_terms))[:6]
        return query + " | related: " + ", ".join(extra_terms)
    return query


def rewrite_query(query: str) -> list[str]:
    """将用户查询改写为多个检索查询"""
    expanded = expand_synonyms(query)

    prompt = REWRITE_PROMPT.format(query=expanded)
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM},
        {"role": "user", "content": prompt}
    ]

    try:
        response = call_llm(messages, temperature=0.5, max_tokens=512)
        queries = []
        for line in response.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            line = re.sub(r'^\d+[\.\)]\s*', '', line)
            line = line.strip('"\'""''')
            if line:
                queries.append(line)
    except Exception as e:
        print(f"  [WARN] 查询改写 LLM 失败，使用降级方案: {e}", file=sys.stderr)
        queries = _fallback_rewrite(expanded)

    result = [query]
    result.extend(queries[:3])
    return result


def _fallback_rewrite(query: str) -> list[str]:
    """LLM 不可用时的降级改写方案"""
    queries = []

    cn_to_en = {
        "如何": "how to", "仿真": "simulation", "分析": "analysis",
        "传输特性": "transfer characteristic", "反相器": "CMOS inverter",
        "放大器": "amplifier", "滤波": "filter", "直流": "DC",
        "交流": "AC", "瞬态": "transient", "噪声": "noise",
        "模型": "model", "参数": "parameter", "网表": "netlist",
        "器件": "device", "电路": "circuit",
    }
    en_query = query
    for cn, en in cn_to_en.items():
        en_query = en_query.replace(cn, en)

    if en_query != query:
        queries.append(en_query)

    # 添加分析类型变体
    analysis_terms = [".tran", ".dc", ".ac"]
    for term in analysis_terms:
        if term not in query.lower():
            queries.append(f"{query} {term}")
            break

    return queries[:3]


def extract_keywords(query: str) -> list[str]:
    """从查询中提取 SPICE 领域关键词"""
    spice_terms = [
        # SPICE 命令
        ".dc", ".ac", ".tran", ".op", ".noise", ".tf", ".four", ".pz",
        ".disto", ".sens", ".mc", ".model", ".subckt", ".control", ".end",
        ".print", ".plot", ".probe", ".measure", ".param", ".include",
        ".global", ".options", ".nodeset", ".ic",
        # 器件
        "MOSFET", "BJT", "diode", "JFET", "MESFET", "resistor", "capacitor",
        "inductor", "transmission line", "switch",
        # 模型
        "BSIM3", "BSIM4", "BSIM-BULK", "BSIM-CMG", "BSIM-SOI",
        "EKV", "VBIC", "HICUM", "MEXTRAM", "PSP",
        # 分析
        "DC analysis", "AC analysis", "transient", "transfer function",
        "noise analysis", "Monte Carlo", "pole-zero", "Fourier",
        "operating point", "sensitivity", "distortion",
        # 应用
        "inverter", "amplifier", "oscillator", "filter", "comparator",
        "ADC", "DAC", "PLL", "bandgap", "LDO", "charge pump",
        # 工具
        "ngspice", "nutmeg", "spice", "XSPICE", "CIDER",
    ]

    found = []
    query_lower = query.lower()
    sorted_terms = sorted(spice_terms, key=len, reverse=True)
    for term in sorted_terms:
        if term.lower() in query_lower:
            found.append(term)
            query_lower = query_lower.replace(term.lower(), "", 1)
    return found


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    else:
        test_query = "如何用 ngspice 仿真一个 CMOS 反相器的传输特性"

    print(f"原始查询: {test_query}")
    print(f"提取关键词: {extract_keywords(test_query)}")
    print(f"同义词扩展: {expand_synonyms(test_query)}")
    print()

    queries = rewrite_query(test_query)
    print(f"改写查询 ({len(queries)} 个):")
    for i, q in enumerate(queries):
        print(f"  [{i}] {q}")
