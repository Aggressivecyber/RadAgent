"""LangGraph StateGraph 构建 — RadG4-Agent 核心图"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from radagent.state import RadAgentState
from radagent.nodes.parse_intent import parse_intent
from radagent.nodes.parameterize import parameterize
from radagent.nodes.build_run import build_and_run
from radagent.nodes.analyze import analyze
from radagent.nodes.report import generate_report, human_review


def build_graph() -> StateGraph:
    """构建并编译 RadG4-Agent 图"""
    builder = StateGraph(RadAgentState)

    # 添加节点
    builder.add_node("parse_intent", parse_intent)
    builder.add_node("parameterize", parameterize)
    builder.add_node("build_and_run", build_and_run)
    builder.add_node("analyze", analyze)
    builder.add_node("generate_report", generate_report)
    builder.add_node("human_review", human_review)

    # 添加边
    builder.add_edge(START, "parse_intent")
    builder.add_edge("parse_intent", "parameterize")
    # parameterize → build_and_run (固定边)
    builder.add_edge("parameterize", "build_and_run")
    # build_and_run 用 Command 动态路由 (重试/成功)
    # analyze → generate_report (固定边)
    builder.add_edge("analyze", "generate_report")
    # generate_report → human_review (固定边)
    builder.add_edge("generate_report", "human_review")
    # human_review 用 Command 动态路由 (批准/反馈)

    # 编译 — checkpointer 保存状态
    checkpointer = MemorySaver()
    graph = builder.compile(checkpointer=checkpointer)

    return graph
