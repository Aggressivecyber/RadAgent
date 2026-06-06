#!/usr/bin/env python3
"""
ngspice SPICE 网表生成模块
- 检索电路示例后，结合用户需求生成 SPICE 网表
- 输出完整 .cir 文件，带中文注释
"""

import json
import sys
import time
import urllib.request
import urllib.error

from ngspice_rag_mcp import search_documents, keyword_search, get_document
from query_rewrite import rewrite_query

# 智谱 LLM API 配置
LLM_API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
LLM_API_KEY = "f5dc034a22df47ac8cf98c37710e0bc6.crvx5afiTuITC247"
LLM_MODEL = "glm-5-turbo"


def call_llm(messages: list[dict], temperature: float = 0.4, max_tokens: int = 8192) -> str:
    """调用智谱 LLM API"""
    payload = json.dumps({
        "model": LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }, ensure_ascii=False).encode('utf-8')

    req = urllib.request.Request(
        LLM_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {LLM_API_KEY}"
        }
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, IndexError) as e:
            if attempt < max_retries - 1:
                print(f"  [RETRY] LLM 调用失败 (attempt {attempt+1}): {e}", file=sys.stderr)
                time.sleep(2)
            else:
                raise RuntimeError(f"LLM 调用失败: {e}") from e


# ============================================================================
# 代码生成系统提示词
# ============================================================================

CODE_GEN_SYSTEM = """你是 ngspice/SPICE 电路仿真脚本生成专家。

你能根据用户需求和参考电路示例，生成完整的 SPICE 网表文件。

支持的元素：
1. 器件定义：MOSFET、BJT、二极管、JFET、电阻、电容、电感、传输线、子电路等
2. 模型定义：.model（BSIM3/4、二极管、BJT 等）
3. 仿真命令：.dc、.ac、.tran、.op、.noise、.tf、.four、.pz 等
4. 控制脚本：.control 块（nutmeg 命令）
5. 测量：.measure 语句
6. 参数化：.param 定义

生成规则：
1. 输出完整的可运行 SPICE 网表
2. 添加清晰的中文注释，解释每个关键步骤
3. 参考提供的电路示例的格式和风格
4. 合理设置默认参数值
5. 使用标准的 SPICE 语法（ngspice 兼容）
6. 第一行必须是标题注释行

输出格式：
- 在 ```spice 代码块中输出网表
- 网表前说明用途
- 网表后说明如何运行（ngspice 命令）"""


# ============================================================================
# 检索相关代码示例
# ============================================================================

def retrieve_code_examples(requirements: str, top_k: int = 8) -> list[dict]:
    """检索与需求相关的电路示例"""
    queries = rewrite_query(requirements)
    all_results = []
    seen_ids = set()

    for q in queries:
        results = search_documents(q, top_k=3)
        for r in results:
            if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                seen_ids.add(r["doc_id"])
                meta = r.get("metadata", {})
                if isinstance(meta, dict) and meta.get("type") == "circuit":
                    all_results.insert(0, r)
                else:
                    all_results.append(r)

    # 关键词补充
    spice_keywords = [".tran", ".dc", ".ac", ".model", ".subckt", ".control",
                      "MOSFET", "BJT", "inverter", "amplifier"]
    req_lower = requirements.lower()
    for sk in spice_keywords:
        if sk.lower() in req_lower:
            kw_results = keyword_search(sk, top_k=3)
            for r in kw_results:
                if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                    seen_ids.add(r["doc_id"])
                    all_results.append(r)

    full_examples = []
    for r in all_results[:5]:
        doc = get_document(r["doc_id"])
        if "error" not in doc:
            full_examples.append(doc)

    return full_examples


# ============================================================================
# 代码生成
# ============================================================================

def generate_spice_code(requirements: str) -> str:
    """根据需求生成 SPICE 网表"""
    examples = retrieve_code_examples(requirements)

    examples_text = ""
    if examples:
        examples_text = "以下是从知识库中检索到的参考电路示例：\n\n"
        for i, ex in enumerate(examples):
            content = ex.get("content", "")
            title = ex.get("title", "Unknown")
            if len(content) > 2000:
                content = content[:2000] + "\n... (代码已截断)"
            examples_text += f"### 示例 {i+1}: {title}\n```\n{content}\n```\n\n"
    else:
        examples_text = "未检索到相关电路示例，请基于通用 SPICE 知识生成。\n"

    user_prompt = f"""用户需求：{requirements}

{examples_text}

请根据以上需求和参考示例，生成完整的 SPICE 网表文件。
要求：
1. 输出可直接用 ngspice 运行的完整网表
2. 每个关键步骤加中文注释（SPICE 注释用 * 号）
3. 合理设置参数默认值
4. 包含合适的仿真命令和输出控制
5. 如涉及器件模型，使用常见的 BSIM 或简单模型参数

请生成 SPICE 网表："""

    messages = [
        {"role": "system", "content": CODE_GEN_SYSTEM},
        {"role": "user", "content": user_prompt}
    ]

    try:
        response = call_llm(messages, temperature=0.3, max_tokens=8192)
        return response
    except RuntimeError as e:
        return f"代码生成失败: {e}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_req = " ".join(sys.argv[1:])
    else:
        test_req = "CMOS inverter transfer characteristic simulation"

    print(f"需求: {test_req}")
    print("=" * 60)

    code = generate_spice_code(test_req)

    print(code)
