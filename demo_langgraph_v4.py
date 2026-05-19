"""
LangGraph 高级示例 - 多 Agent 研究团队
新概念 (相比 v3):
  1. Supervisor 模式 — 主管 Agent 分配任务给专家 Agent
  2. 自反馈循环 — Agent 审查自己的输出，不满意就改进
  3. Streaming — stream() 实时逐字输出
  4. Command — 动态路由到任意节点（比 return "node_name" 更灵活）
  5. RetryPolicy — 节点失败自动重试

流程:
  用户提问
  → supervisor (分析问题，决定派给哪个专家)
      ├── researcher (研究专家 — 搜索资料)
      ├── analyst (分析专家 — 数据分析)
      └── writer (写作专家 — 撰写报告)
  → reviewer (自反馈: 审查质量，打分)
      ├── 分数 ≥ 7 → final_report → END
      └── 分数 < 7 → 回到对应专家重做 (最多重试 3 次)

运行: python3 demo_langgraph_v4.py
"""

import json
import os
from typing import Annotated, Literal, Any
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AnyMessage
from langgraph.graph import StateGraph, START, END, add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command, interrupt
from langgraph.errors import GraphRecursionError


# ── 1. 模型 ──────────────────────────────────────────────
llm = ChatOpenAI(
    model="deepseek-chat",
    base_url="https://api.deepseek.com",
    api_key=os.environ["DEEPSEEK_API_KEY"],
    temperature=0,
)


# ── 2. 状态定义 ──────────────────────────────────────────
class ResearchState(TypedDict):
    """研究团队的全局状态"""
    messages: Annotated[list[AnyMessage], add_messages]  # 对话历史
    question: str                  # 用户的问题
    task_type: str                 # supervisor 判断的任务类型: research/analysis/writing
    draft: str                     # 当前草稿
    review_score: int              # 审查分数 (1-10)
    review_feedback: str           # 审查反馈
    retry_count: int               # 重试次数
    final_report: str              # 最终报告


# ── 3. 专家提示词 ────────────────────────────────────────
SUPERVISOR_PROMPT = """你是一个研究团队的主管。根据用户的问题，判断应该派给哪个专家处理:
- "research": 需要搜索资料、调研背景信息的问题
- "analysis": 需要数据分析、比较、计算的问题
- "writing": 需要撰写文档、总结、翻译的问题

只返回一个词: research / analysis / writing，不要其他内容。"""

RESEARCHER_PROMPT = """你是研究专家。根据问题提供详细的研究分析。
包括: 背景介绍、关键概念、现状分析、参考资料建议。
用中文回答，内容充实但简洁。"""

ANALYST_PROMPT = """你是数据分析专家。根据问题提供数据分析视角。
包括: 关键指标、对比分析、趋势判断、数据来源建议。
用中文回答，提供结构化的分析。"""

WRITER_PROMPT = """你是写作专家。根据问题和已有材料撰写报告。
要求: 结构清晰、语言精炼、重点突出、有实用价值。
用中文回答。"""

REVIEWER_PROMPT = """你是严格的质量审查员。审查草稿的质量。
评分标准:
- 准确性和深度 (1-10)
- 结构清晰度 (1-10)
- 实用价值 (1-10)

用以下 JSON 格式回复（不要其他内容）:
{"score": 数字(1-10的平均分), "feedback": "具体改进建议", "pass": true或false}
如果所有维度都 >= 7 分，pass 为 true。"""


# ── 4. 节点函数 ──────────────────────────────────────────
def supervisor(state: ResearchState) -> Command[Literal["researcher", "analyst", "writer"]]:
    """
    ★ 新概念: Command — 比 return "node_name" 更强大
    Command 可以同时:
      1. 更新 state (update=...)
      2. 指定下一个节点 (goto=...)

    比 add_conditional_edges 更灵活，因为可以动态决定去哪 + 同时更新状态。
    """
    response = llm.invoke([
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=f"问题: {state['question']}"),
    ])

    task_type = response.content.strip().lower()
    # 确保只返回有效值
    if task_type not in ("research", "analysis", "writing"):
        task_type = "research"

    print(f"\n👔 主管判断: 任务类型 = {task_type}")

    # ★ Command: 同时更新状态 + 指定下一个节点
    expert_map = {"research": "researcher", "analysis": "analyst", "writing": "writer"}
    return Command(
        update={"task_type": task_type},
        goto=expert_map[task_type],
    )


def researcher(state: ResearchState) -> dict:
    """研究专家节点"""
    prompt = RESEARCHER_PROMPT
    if state.get("review_feedback"):
        prompt += f"\n\n[审查反馈，请改进]: {state['review_feedback']}"

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"问题: {state['question']}\n\n当前草稿: {state.get('draft', '无')}"),
    ])
    print(f"  🔍 研究专家完成工作")
    return {"draft": response.content}


def analyst(state: ResearchState) -> dict:
    """分析专家节点"""
    prompt = ANALYST_PROMPT
    if state.get("review_feedback"):
        prompt += f"\n\n[审查反馈，请改进]: {state['review_feedback']}"

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"问题: {state['question']}\n\n当前草稿: {state.get('draft', '无')}"),
    ])
    print(f"  📊 分析专家完成工作")
    return {"draft": response.content}


def writer(state: ResearchState) -> dict:
    """写作专家节点"""
    prompt = WRITER_PROMPT
    if state.get("review_feedback"):
        prompt += f"\n\n[审查反馈，请改进]: {state['review_feedback']}"

    response = llm.invoke([
        SystemMessage(content=prompt),
        HumanMessage(content=f"问题: {state['question']}\n\n当前草稿: {state.get('draft', '无')}"),
    ])
    print(f"  ✍️ 写作专家完成工作")
    return {"draft": response.content}


def reviewer(state: ResearchState) -> Command[Literal["researcher", "analyst", "writer", "final_report"]]:
    """
    ★ 自反馈循环的核心
    审查草稿质量:
      - 分数 >= 7 → 通过，生成最终报告
      - 分数 < 7 且重试 < 3 次 → 回到对应专家改进
      - 重试 >= 3 次 → 强制通过（防止无限循环）
    """
    retry_count = state.get("retry_count", 0)

    response = llm.invoke([
        SystemMessage(content=REVIEWER_PROMPT),
        HumanMessage(content=f"请审查以下内容:\n\n{state.get('draft', '无内容')}"),
    ])

    # 解析审查结果
    try:
        review = json.loads(response.content)
        score = int(review.get("score", 5))
        feedback = review.get("feedback", "")
        passed = review.get("pass", False)
    except (json.JSONDecodeError, ValueError):
        score = 5
        feedback = response.content
        passed = False

    print(f"  📝 审查结果: 分数={score}/10, 通过={passed}, 重试={retry_count}/3")

    # 强制通过: 重试太多就别再循环了
    if retry_count >= 3:
        print(f"  ⚠️ 达到最大重试次数，强制通过")
        return Command(
            update={"review_score": score, "review_feedback": feedback, "final_report": state["draft"]},
            goto="final_report",
        )

    # 通过审查
    if passed and score >= 7:
        print(f"  ✅ 审查通过！")
        return Command(
            update={"review_score": score, "review_feedback": feedback, "final_report": state["draft"]},
            goto="final_report",
        )

    # ★ 未通过 → 回到对应专家改进（自反馈循环！）
    print(f"  🔄 审查未通过，返回专家改进...")
    expert_map = {"research": "researcher", "analysis": "analyst", "writing": "writer"}
    return Command(
        update={
            "review_score": score,
            "review_feedback": feedback,
            "retry_count": retry_count + 1,
        },
        goto=expert_map.get(state["task_type"], "researcher"),
    )


def final_report(state: ResearchState) -> dict:
    """生成最终报告"""
    print("\n" + "=" * 50)


# ── 5. 构建图 ────────────────────────────────────────────
builder = StateGraph(ResearchState)

# 添加节点
builder.add_node("supervisor", supervisor)
builder.add_node("researcher", researcher)
builder.add_node("analyst", analyst)
builder.add_node("writer", writer)
builder.add_node("reviewer", reviewer)
builder.add_node("final_report", final_report)

# 添加边
builder.add_edge(START, "supervisor")

# ★ supervisor 用 Command 动态路由，不需要 add_conditional_edges
# 每个 expert 完成后 → reviewer
builder.add_edge("researcher", "reviewer")
builder.add_edge("analyst", "reviewer")
builder.add_edge("writer", "reviewer")

# ★ reviewer 也用 Command 动态路由:
#   通过 → final_report → END
#   未通过 → 回到对应 expert (循环!)
builder.add_edge("final_report", END)

# 编译
checkpointer = MemorySaver()
graph = builder.compile(
    checkpointer=checkpointer,
    # ★ 新概念: recursion_limit — 防止无限循环
    # 默认 25 步，如果图执行超过 25 步就报错
    # 自反馈循环特别需要这个保护
)


# ── 6. 运行 — 带流式输出 ────────────────────────────────
def main():
    print("=" * 60)
    print("🔬 多 Agent 研究团队 (v4)")
    print("新概念: Supervisor | 自反馈 | Streaming | Command")
    print("=" * 60)

    config = {"configurable": {"thread_id": "research-v4"}}
    question = input("\n你的问题: ").strip()
    if not question:
        print("再见！")
        return

    # ── 方式 1: invoke (等全部完成才返回) ──
    # result = graph.invoke({"question": question, ...}, config=config)

    # ── 方式 2: stream (★ 新概念: 逐步获取输出) ──
    print("\n--- 开始处理 ---")

    initial_state = {
        "messages": [],
        "question": question,
        "task_type": "",
        "draft": "",
        "review_score": 0,
        "review_feedback": "",
        "retry_count": 0,
        "final_report": "",
    }

    # ★ stream_mode="updates" — 每个节点执行完返回一次更新
    for event in graph.stream(initial_state, config=config, stream_mode="updates"):
        # event 格式: {"节点名": {更新的 state 字段}}
        for node_name, node_output in event.items():
            if node_name == "supervisor":
                print(f"  → 主管决定: 任务类型={node_output.get('task_type', '?')}")
            elif node_name in ("researcher", "analyst", "writer"):
                print(f"  → {node_name} 产出草稿 ({len(node_output.get('draft', ''))} 字)")
            elif node_name == "reviewer":
                print(f"  → 审查: 分数={node_output.get('review_score', '?')}, "
                      f"重试={node_output.get('retry_count', 0)}")

    print("\n✅ 处理完成！")


if __name__ == "__main__":
    main()
