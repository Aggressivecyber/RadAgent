#!/usr/bin/env python3
"""
TCAD ReAct Agent — 思维链推理 Agent
- Thought → Action → Observation 循环
- 工具选择：search_tcad, keyword_search, get_document, list_sources
- 自我评估结果是否足够回答问题
- 最多 5 轮迭代
"""

import json
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_base.llm_client import call_llm
from knowledge_base.tcad.query_rewrite import extract_keywords, rewrite_query
from knowledge_base.tcad.tcad_rag_mcp import (
    get_document,
    keyword_search,
    list_sources,
    search_documents,
)

MAX_ITERATIONS = 5


# ============================================================================
# Agent 系统提示词
# ============================================================================

AGENT_SYSTEM_PROMPT = """你是 TCAD Sentaurus 半导体仿真领域的专家助手。

你可以使用以下工具来查找信息：

1. search_tcad(query, top_k) — 语义搜索 TCAD 文档和代码
   用途：查找手册说明、教程、代码示例
   参数：query(搜索词), top_k(结果数，默认5)

2. keyword_search(keyword, top_k) — 关键词精确搜索
   用途：查找特定命令、参数名、文件名
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
- 引用具体的文档来源。
- 用中文回答，技术术语保留英文。"""


# ============================================================================
# 工具执行器
# ============================================================================

def execute_tool(action_name: str, params: dict) -> str:
    """执行单个工具调用，返回格式化结果"""
    try:
        if action_name == "search_tcad":
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
            results = keyword_search(keyword, top_k)
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


def parse_action(text: str) -> tuple[str | None, dict | None]:
    """从 Agent 输出中解析 Action 行，返回 (工具名, 参数dict)"""
    # 匹配 Action: tool_name(param1="value1", param2=value2)
    match = re.search(r'Action:\s*(\w+)\((.+?)\)', text, re.DOTALL)
    if not match:
        # 尝试宽松匹配：Action: tool_name
        match = re.search(r'Action:\s*(\w+)', text)
        if match:
            return match.group(1), {}
        return None, None

    tool_name = match.group(1)
    params_str = match.group(2).strip()

    # 解析参数
    params = {}
    # 匹配 key="value" 或 key=value
    for pm in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', params_str):
        params[pm.group(1)] = pm.group(2)
    for pm in re.finditer(r"(\w+)\s*=\s*'([^']*)'", params_str):
        params[pm.group(1)] = pm.group(2)
    for pm in re.finditer(r'(\w+)\s*=\s*(\d+)', params_str):
        params[pm.group(1)] = int(pm.group(2))

    # 如果没有解析到 query 参数，把整个参数字符串作为 query
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
    """
    运行 ReAct Agent 回答用户问题。

    Args:
        query: 用户问题
        verbose: 是否打印推理过程

    Returns:
        Agent 的最终回答
    """
    # 初始化对话消息
    messages = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
    ]

    # 先用查询改写获取多个检索查询，做第一轮搜索
    rewritten_queries = rewrite_query(query)
    if verbose:
        print(f"\n[查询改写] 生成 {len(rewritten_queries)} 个查询:")
        for i, q in enumerate(rewritten_queries):
            print(f"  [{i}] {q}")

    # 第一轮：多查询检索
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
            kw_results = keyword_search(kw, top_k=3)
            for r in kw_results:
                if isinstance(r, dict) and "doc_id" in r and r["doc_id"] not in seen_ids:
                    seen_ids.add(r["doc_id"])
                    initial_results.append(r)

    # 格式化初始搜索结果
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

    # 构建 Agent 的第一条消息
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

        # 调用 LLM
        try:
            response = call_llm(messages, temperature=0.2)
        except RuntimeError as e:
            return f"LLM 调用失败: {e}"

        if verbose:
            # 只打印 Thought 和 Action 部分
            for line in response.split('\n')[:5]:
                print(f"  {line}")

        # 检查是否有最终回答
        answer = has_final_answer(response)
        if answer:
            if verbose:
                print(f"\n[Agent 完成] 经过 {iteration + 1} 轮迭代")
            return answer

        # 解析 Action
        tool_name, params = parse_action(response)

        if tool_name is None:
            # 没有找到 Action 也没有 Answer，尝试把整个回复作为最终回答
            if len(response) > 50:
                if verbose:
                    print("\n[Agent 完成] 直接返回（无明确 Action/Answer 标记）")
                return response
            # LLM 输出异常，追加引导
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user",
                "content": "请继续分析。如果已有足够信息，用 'Answer:' 给出最终回答。如果需要更多信息，用 'Action:' 调用工具。"
            })
            continue

        # 执行工具
        if verbose:
            param_str = json.dumps(params, ensure_ascii=False)
            print(f"  [执行] {tool_name}({param_str})")

        observation = execute_tool(tool_name, params)

        # 截断过长的 observation（避免超出上下文窗口）
        if len(observation) > 3000:
            observation = observation[:3000] + "\n...(内容已截断)"

        # 将这一轮的交互加入消息历史
        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": f"Observation: {observation}"})

        if verbose:
            print(f"  [结果] {len(observation)} 字符")

    # 超过最大迭代次数，强制总结
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


# ============================================================================
# 命令行测试
# ============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    else:
        test_query = "如何设置 NMOS 辐照陷阱模型"

    print(f"问题: {test_query}")
    print("=" * 60)

    answer = run_agent(test_query, verbose=True)

    print("\n" + "=" * 60)
    print("最终回答:")
    print(answer)
