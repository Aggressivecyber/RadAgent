#!/usr/bin/env python3
"""
TCAD 代码生成模块
- 检索代码示例后，结合用户需求生成/修改 TCAD 脚本
- 支持 SDE（结构定义）+ SProcess（工艺）+ SDevice（器件仿真）
- 输出完整 .cmd 文件，带中文注释
"""

import json
import sys
import time
import urllib.request
import urllib.error

from tcad_rag_mcp import search_documents, keyword_search, get_document
from query_rewrite import rewrite_query

# 智谱 LLM API 配置
LLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
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

CODE_GEN_SYSTEM = """你是 TCAD Sentaurus 仿真脚本生成专家。

你能根据用户需求和参考代码示例，生成完整的 TCAD 仿真脚本。

支持的脚本类型：
1. SDE (.tcl) — Sentaurus Structure Editor，定义器件几何结构和网格
2. SProcess (.cmd) — Sentaurus Process，定义工艺流程（离子注入、扩散、刻蚀等）
3. SDevice (.cmd) — Sentaurus Device，定义器件仿真（物理模型、偏置、求解）

生成规则：
1. 输出完整的可运行脚本，包含所有必要的参数
2. 添加清晰的中文注释，解释每个关键步骤
3. 参考提供的代码示例的格式和风格
4. 合理设置默认参数值
5. 使用标准的 TCAD 命令语法

输出格式：
- 在 ```cmd 或 ```tcl 代码块中输出脚本
- 脚本前说明用途和参数
- 脚本后说明如何运行"""


# ============================================================================
# 检索相关代码示例
# ============================================================================

def retrieve_code_examples(requirements: str, top_k: int = 8) -> list[dict]:
    """检索与需求相关的代码示例"""
    # 用改写查询搜索
    queries = rewrite_query(requirements)
    all_results = []
    seen_ids = set()

    for q in queries:
        # 语义搜索
        results = search_documents(q, top_k=3)
        for r in results:
            if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                seen_ids.add(r["doc_id"])
                # 优先选择代码文件
                meta = r.get("metadata", {})
                if isinstance(meta, dict) and meta.get("type") == "code":
                    all_results.insert(0, r)  # 代码排前面
                else:
                    all_results.append(r)

    # 关键词补充搜索（聚焦代码）
    code_keywords = ["sprocess", "sdevice", "sde", ".cmd", ".tcl"]
    req_lower = requirements.lower()
    for ck in code_keywords:
        if ck in req_lower:
            kw_results = keyword_search(ck, top_k=3)
            for r in kw_results:
                if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                    seen_ids.add(r["doc_id"])
                    all_results.append(r)

    # 获取代码示例的完整内容（只取前 5 个）
    full_examples = []
    for r in all_results[:5]:
        doc = get_document(r["doc_id"])
        if "error" not in doc:
            full_examples.append(doc)

    return full_examples


# ============================================================================
# 代码生成
# ============================================================================

def generate_tcad_code(requirements: str) -> str:
    """
    根据需求生成 TCAD 仿真脚本。

    Args:
        requirements: 用户需求描述（中文/英文）

    Returns:
        生成的代码和说明
    """
    # 1. 检索相关代码示例
    examples = retrieve_code_examples(requirements)

    # 2. 组装参考代码
    examples_text = ""
    if examples:
        examples_text = "以下是从知识库中检索到的参考代码示例：\n\n"
        for i, ex in enumerate(examples):
            content = ex.get("content", "")
            title = ex.get("title", "Unknown")
            # 截断过长的示例（保留 2000 字符）
            if len(content) > 2000:
                content = content[:2000] + "\n... (代码已截断)"
            examples_text += f"### 示例 {i+1}: {title}\n```\n{content}\n```\n\n"
    else:
        examples_text = "未检索到相关代码示例，请基于通用 TCAD 知识生成。\n"

    # 3. 构建 LLM 提示
    user_prompt = f"""用户需求：{requirements}

{examples_text}

请根据以上需求和参考示例，生成完整的 TCAD 仿真脚本。
要求：
1. 输出可直接运行的完整脚本
2. 每个关键步骤加中文注释
3. 合理设置参数默认值
4. 如果需求涉及完整流程，按 SDE → SProcess → SDevice 顺序生成

请生成代码："""

    messages = [
        {"role": "system", "content": CODE_GEN_SYSTEM},
        {"role": "user", "content": user_prompt}
    ]

    # 4. 调用 LLM 生成代码
    try:
        response = call_llm(messages, temperature=0.3, max_tokens=8192)
        return response
    except RuntimeError as e:
        return f"代码生成失败: {e}"


# ============================================================================
# 命令行测试
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_req = " ".join(sys.argv[1:])
    else:
        test_req = "CMOS inverter, 45nm, TID 100krad 辐射效应仿真"

    print(f"需求: {test_req}")
    print("=" * 60)

    code = generate_tcad_code(test_req)

    print(code)
