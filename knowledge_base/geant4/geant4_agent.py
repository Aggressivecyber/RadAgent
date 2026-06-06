#!/usr/bin/env python3
"""
Geant4 ReAct Agent — 思维链推理 Agent
- Thought → Action → Observation 循环
- 工具：search_geant4, keyword_search, get_document, list_sources
- 自我评估结果是否足够回答问题
- 最多 5 轮迭代
"""

import json
import re
import sys
import time
import urllib.request
import urllib.error

from geant4_rag_mcp import search_documents, keyword_search_func, get_document, list_sources
from query_rewrite import rewrite_query, extract_keywords

# 智谱 LLM API 配置
LLM_API_URL = "https://open.bigmodel.cn/api/coding/paas/v4/chat/completions"
LLM_API_KEY = "f5dc034a22df47ac8cf98c37710e0bc6.crvx5afiTuITC247"
LLM_MODEL = "glm-5-turbo"
MAX_ITERATIONS = 5


# ============================================================================
# LLM 调用
# ============================================================================

def call_llm(messages: list[dict], temperature: float = 0.3, max_tokens: int = 4096) -> str:
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 10 * (attempt + 1)
                print(f"  [RATE LIMIT] 等待 {wait}s 后重试...", file=sys.stderr)
                if attempt < max_retries - 1:
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"LLM 调用失败: 速率限制") from e
            elif attempt < max_retries - 1:
                print(f"  [RETRY] LLM 调用失败 (attempt {attempt+1}): {e}", file=sys.stderr)
                time.sleep(3)
            else:
                raise RuntimeError(f"LLM 调用失败: {e}") from e
        except (urllib.error.URLError, KeyError, json.JSONDecodeError, IndexError) as e:
            if attempt < max_retries - 1:
                print(f"  [RETRY] LLM 调用失败 (attempt {attempt+1}): {e}", file=sys.stderr)
                time.sleep(3)
            else:
                raise RuntimeError(f"LLM 调用失败: {e}") from e


# ============================================================================
# Agent 系统提示词
# ============================================================================

AGENT_SYSTEM_PROMPT = """你是 Geant4 蒙特卡洛粒子输运仿真领域的专家助手。

你可以使用以下工具来查找信息：

1. search_geant4(query, top_k) — 语义搜索 Geant4 文档和代码示例
   用途：查找手册说明、教程、示例代码
   参数：query(搜索词), top_k(结果数，默认5)

2. keyword_search(keyword, top_k) — 关键词精确搜索
   用途：查找特定类名、方法名、参数
   参数：keyword(关键词), top_k(结果数，默认10)

3. get_document(doc_id) — 获取完整文档
   用途：查看搜索结果中某个文档的完整内容
   参数：doc_id(文档ID)

4. list_sources() — 列出数据源统计
   用途：了解可用的文档来源和数量

每次回复格式：
Thought: [分析当前情况，思考下一步]
Action: [工具名(参数)]
或
Answer: [最终回答]

关键规则：
- 先搜索，后回答。不要凭记忆回答技术细节。
- 每次只调用一个工具。
- 如果搜索结果不够，换不同关键词或工具重试。
- 引用具体的文档来源和代码示例。
- 用中文回答，技术术语和 Geant4 类名保留英文。
- 涉及代码时给出完整的 C++ 代码片段。"""


# ============================================================================
# 工具执行器
# ============================================================================

def execute_tool(action_name: str, params: dict) -> str:
    """执行单个工具调用"""
    try:
        if action_name in ("search_geant4", "search_tcad", "search"):
            query = params.get("query", "")
            top_k = params.get("top_k", 5)
            results = search_documents(query, top_k)
            if not results:
                return "搜索无结果。"
            parts = []
            for r in results:
                parts.append(
                    f"[ID:{r['doc_id']}] {r['title']}\n"
                    f"来源: {r['source']} | 相关度: {r['relevance_score']}\n"
                    f"{r['content']}\n"
                )
            return "\n---\n".join(parts)

        elif action_name == "keyword_search":
            keyword = params.get("keyword", "")
            top_k = params.get("top_k", 10)
            results = keyword_search_func(keyword, top_k)
            if not results:
                return "关键词搜索无结果。"
            parts = []
            for r in results:
                parts.append(
                    f"[ID:{r['doc_id']}] {r['title']}\n"
                    f"来源: {r['source']}\n"
                    f"{r['content']}\n"
                )
            return "\n---\n".join(parts)

        elif action_name == "get_document":
            doc_id = params.get("doc_id")
            if doc_id is None:
                return "错误：缺少 doc_id 参数"
            doc = get_document(int(doc_id))
            if "error" in doc:
                return f"获取文档失败: {doc['error']}"
            return (
                f"ID: {doc['doc_id']}\n"
                f"标题: {doc['title']}\n"
                f"来源: {doc['source']}\n\n"
                f"{doc['content']}"
            )

        elif action_name == "list_sources":
            info = list_sources()
            text = f"总文档块数: {info['total_chunks']}\n"
            text += f"数据库大小: {info['database_size_mb']} MB\n"
            for source, count in info.get("sources", {}).items():
                text += f"  - {source}: {count} 块\n"
            return text

        else:
            return f"未知工具: {action_name}"

    except Exception as e:
        return f"工具执行错误: {e}"


# ============================================================================
# 解析 Agent 输出
# ============================================================================

def parse_action(text: str) -> tuple[str | None, dict | None]:
    """从 Agent 输出中解析 Action 行"""
    match = re.search(r'Action:\s*(\w+)\((.+?)\)', text, re.DOTALL)
    if not match:
        match = re.search(r'Action:\s*(\w+)', text)
        if match:
            return match.group(1), {}
        return None, None

    tool_name = match.group(1)
    params_str = match.group(2).strip()

    params = {}
    for pm in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', params_str):
        params[pm.group(1)] = pm.group(2)
    for pm in re.finditer(r"(\w+)\s*=\s*'([^']*)'", params_str):
        params[pm.group(1)] = pm.group(2)
    for pm in re.finditer(r'(\w+)\s*=\s*(\d+)', params_str):
        params[pm.group(1)] = int(pm.group(2))

    if not params and params_str:
        params["query"] = params_str.strip('"').strip("'")

    return tool_name, params


def has_final_answer(text: str) -> str | None:
    """检查是否包含最终回答"""
    match = re.search(r'Answer:\s*(.+)', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


# ============================================================================
# ReAct Agent 主循环
# ============================================================================

def run_agent(query: str, verbose: bool = False) -> str:
    """运行 ReAct Agent"""
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]

    # 多查询检索
    rewritten_queries = rewrite_query(query)
    if verbose:
        print(f"\n[查询改写] 生成 {len(rewritten_queries)} 个查询:")
        for i, q in enumerate(rewritten_queries):
            print(f"  [{i}] {q}")

    initial_results = []
    seen_ids = set()
    for rq in rewritten_queries:
        results = search_documents(rq, top_k=3)
        for r in results:
            if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                seen_ids.add(r["doc_id"])
                initial_results.append(r)

    # 关键词补充搜索
    keywords = extract_keywords(query)
    if keywords:
        for kw in keywords[:3]:
            kw_results = keyword_search_func(kw, top_k=3)
            for r in kw_results:
                if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                    seen_ids.add(r["doc_id"])
                    initial_results.append(r)

    if initial_results:
        obs_text = "初始检索结果：\n"
        for r in initial_results[:8]:
            obs_text += (
                f"\n[ID:{r['doc_id']}] {r['title']}\n"
                f"来源: {r['source']}"
            )
            if 'relevance_score' in r:
                obs_text += f" | 相关度: {r['relevance_score']}"
            content = r.get('content', '')
            obs_text += f"\n{content[:600]}\n"
    else:
        obs_text = "初始检索无结果。"

    first_message = (
        f"用户问题：{query}\n\n"
        f"Observation: {obs_text}\n\n"
        f"请分析搜索结果，判断是否足够回答问题。如果需要更多信息，使用工具继续搜索。"
    )
    messages.append({"role": "user", "content": first_message})

    if verbose:
        print(f"\n[初始检索] 找到 {len(initial_results)} 个相关文档")

    # ReAct 循环
    for iteration in range(MAX_ITERATIONS):
        if verbose:
            print(f"\n--- 迭代 {iteration + 1}/{MAX_ITERATIONS} ---")

        try:
            response = call_llm(messages, temperature=0.2)
        except RuntimeError as e:
            return f"LLM 调用失败: {e}"

        if verbose:
            for line in response.split('\n')[:5]:
                print(f"  {line}")

        answer = has_final_answer(response)
        if answer:
            if verbose:
                print(f"\n[Agent 完成] 经过 {iteration + 1} 轮迭代")
            return answer

        tool_name, params = parse_action(response)

        if tool_name is None:
            if len(response) > 50:
                if verbose:
                    print(f"\n[Agent 完成] 直接返回")
                return response
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": "请继续分析。如果已有足够信息，用 'Answer:' 给出最终回答。如果需要更多信息，用 'Action:' 调用工具。"
            })
            continue

        if verbose:
            param_str = json.dumps(params, ensure_ascii=False)
            print(f"  [执行] {tool_name}({param_str})")

        observation = execute_tool(tool_name, params)

        if len(observation) > 3000:
            observation = observation[:3000] + "\n...(内容已截断)"

        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": f"Observation: {observation}"})

        if verbose:
            print(f"  [结果] {len(observation)} 字符")

    # 超过最大迭代次数
    if verbose:
        print(f"\n[Agent] 达到最大迭代次数 {MAX_ITERATIONS}，强制总结")

    messages.append({
        "role": "user",
        "content": "已达到最大搜索次数。请根据已获取的信息给出最终回答。如果信息不足，请说明缺少什么。"
    })

    try:
        final_response = call_llm(messages, temperature=0.3)
        answer = has_final_answer(final_response)
        return answer if answer else final_response
    except RuntimeError as e:
        return f"Agent 总结失败: {e}"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    else:
        test_query = "如何用 Geant4 模拟硅中 TID 辐射产生的 LET 分布"

    print(f"问题: {test_query}")
    print("=" * 60)

    answer = run_agent(test_query, verbose=True)

    print("\n" + "=" * 60)
    print("最终回答:")
    print(answer)
