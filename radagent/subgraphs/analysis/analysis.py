"""分析子图: analyze_data → draw_geometry → draw_heatmap → draw_spectrum

独立子图，可单独调试。主图将其作为一个节点嵌入。
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from radagent.subgraphs.analysis.state import AnalysisState
from radagent.subgraphs.analysis.analyze_data import analyze_data
from radagent.subgraphs.analysis.draw_geometry import draw_geometry
from radagent.subgraphs.analysis.draw_heatmap import draw_heatmap
from radagent.subgraphs.analysis.draw_spectrum import draw_spectrum


def build_analysis_subgraph():
    """构建分析子图"""
    builder = StateGraph(AnalysisState)

    builder.add_node("analyze_data", analyze_data)
    builder.add_node("draw_geometry", draw_geometry)
    builder.add_node("draw_heatmap", draw_heatmap)
    builder.add_node("draw_spectrum", draw_spectrum)

    builder.add_edge(START, "analyze_data")
    # analyze_data → draw_geometry (Command)
    # draw_geometry → draw_heatmap (Command)
    # draw_heatmap → draw_spectrum (Command)
    # draw_spectrum → END (Command)

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)
