"""调研子图: parse_intent → design_schema → define_custom → research_params → research_qc → confirm_params
                                ↑                                              ↑
                            revise ─────────────────────────────────────────────┘

独立子图，可单独调试。主图将其作为一个节点嵌入。
research_qc 失败时转到 revise 节点，revise 分析后路由到对应生产节点。
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from radagent.subgraphs.research.state import ResearchState
from radagent.subgraphs.research.parse_intent import parse_intent
from radagent.subgraphs.research.design_schema import design_schema
from radagent.subgraphs.research.define_custom import define_custom
from radagent.subgraphs.research.research_params import research_params
from radagent.subgraphs.research.research_qc import research_qc
from radagent.subgraphs.research.confirm_params import confirm_params
from radagent.subgraphs.research.revise import revise


def build_research_subgraph():
    """构建调研子图"""
    builder = StateGraph(ResearchState)

    builder.add_node("parse_intent", parse_intent)
    builder.add_node("design_schema", design_schema)
    builder.add_node("define_custom", define_custom)
    builder.add_node("research_params", research_params)
    builder.add_node("research_qc", research_qc)
    builder.add_node("revise", revise)
    builder.add_node("confirm_params", confirm_params)

    builder.add_edge(START, "parse_intent")
    # parse_intent → design_schema (Command)
    # design_schema → define_custom | research_params (按是否有未解析项)
    # define_custom → research_params (Command)
    # research_params → research_qc (Command)
    # research_qc: pass → confirm_params, fail → revise
    # revise → parse_intent | design_schema | research_params (根据反馈路由)
    # confirm_params → END | confirm_params (Command)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
