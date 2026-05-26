"""LangGraph StateGraph 构建 — RadG4-Agent 主图"""

import logging
import sqlite3

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from radagent.state import RadAgentState
from radagent.subgraphs.research.research import build_research_subgraph
from radagent.subgraphs.analysis.analysis import build_analysis_subgraph
from radagent.nodes.parameterize import parameterize
from radagent.nodes.build_run import build_and_run
from radagent.nodes.revise import revise
from radagent.nodes.report import generate_report, human_review
from radagent.nodes.gates import sim_gate, report_gate

logger = logging.getLogger("radagent.node.tools")

_SCHEMA_ALLOWLIST = {
    ("radagent.schemas", "ShieldLayer"),
    ("radagent.schemas", "ShieldGeometry"),
    ("radagent.schemas", "OrbitEnvironment"),
    ("radagent.schemas", "ParticleSource"),
    ("radagent.schemas", "SimulationScenario"),
    ("radagent.schemas", "SimulationPlan"),
    ("radagent.schemas", "BuildResult"),
    ("radagent.schemas", "SimulationResult"),
    ("radagent.schemas", "AnomalyCheck"),
    ("radagent.schemas", "ControlState"),
    ("radagent.schemas", "GateResult"),
}


def build_graph() -> StateGraph:
    """构建并编译 RadG4-Agent 主图"""
    logger.info("构建 LangGraph 主图")
    builder = StateGraph(RadAgentState)

    research_subgraph = build_research_subgraph()
    analysis_subgraph = build_analysis_subgraph()

    builder.add_node("research", research_subgraph)
    builder.add_node("parameterize", parameterize)
    builder.add_node("build_and_run", build_and_run)
    builder.add_node("sim_gate", sim_gate)
    builder.add_node("revise", revise)
    builder.add_node("analyze", analysis_subgraph)
    builder.add_node("report_gate", report_gate)
    builder.add_node("generate_report", generate_report)
    builder.add_node("human_review", human_review)

    # 主图拓扑
    builder.add_edge(START, "research")
    builder.add_edge("research", "parameterize")
    builder.add_edge("parameterize", "build_and_run")
    builder.add_edge("build_and_run", "sim_gate")
    # sim_gate: pass→analyze, fail→revise
    builder.add_edge("analyze", "report_gate")
    # report_gate: pass→human_review, fail→revise
    builder.add_edge("generate_report", "human_review")
    # human_review: pass→END, fail→research
    # revise → research | parameterize | build_and_run | generate_report (Command)

    from radagent.config import CHECKPOINT_DB
    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
    serde = JsonPlusSerializer(allowed_msgpack_modules=_SCHEMA_ALLOWLIST)
    checkpointer = SqliteSaver(conn, serde=serde)
    graph = builder.compile(checkpointer=checkpointer)
    logger.info("主图编译完成")

    return graph
