"""LangGraph subgraph for executing RadAgent agent tools."""

from __future__ import annotations

import ast
import json
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agent_core.agent_tools.registry import get_agent_tool_registry
from agent_core.agent_tools.selection import select_agent_tool_calls


class AgentToolState(TypedDict, total=False):
    user_message: str
    messages: list[Any]
    tool_results: list[dict[str, Any]]


def build_agent_tool_graph() -> StateGraph:
    """Build a reusable LangGraph subgraph that executes selected agent tools."""
    graph = StateGraph(AgentToolState)
    graph.add_node("select_tools", _select_tools_node)
    graph.add_node("execute_tools", ToolNode(get_agent_tool_registry().all()))
    graph.add_node("collect_results", _collect_results_node)
    graph.set_entry_point("select_tools")
    graph.add_conditional_edges(
        "select_tools",
        _route_after_select_tools,
        {
            "execute_tools": "execute_tools",
            "collect_results": "collect_results",
        },
    )
    graph.add_edge("execute_tools", "collect_results")
    graph.add_edge("collect_results", END)
    return graph


async def run_agent_tools(user_message: str) -> list[dict[str, Any]]:
    """Execute any tools selected for this user message and return result payloads."""
    return run_agent_tools_sync(user_message)


def run_agent_tools_sync(user_message: str) -> list[dict[str, Any]]:
    """Synchronous agent-tool execution for worker threads and tests."""
    graph = build_agent_tool_graph().compile()
    result = graph.invoke({"user_message": user_message})
    return list(result.get("tool_results") or [])


def _select_tools_node(state: AgentToolState) -> dict[str, Any]:
    calls = select_agent_tool_calls(str(state.get("user_message") or ""))
    if not calls:
        return {"messages": []}
    return {"messages": [AIMessage(content="", tool_calls=calls)]}


def _route_after_select_tools(state: AgentToolState) -> str:
    return "execute_tools" if state.get("messages") else "collect_results"


def _collect_results_node(state: AgentToolState) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for message in state.get("messages") or []:
        if not isinstance(message, ToolMessage):
            continue
        parsed = _parse_tool_content(str(message.content))
        success = not (isinstance(parsed, dict) and parsed.get("error"))
        results.append(
            {
                "tool": str(message.name or ""),
                "success": success,
                "payload": parsed,
                "tool_call_id": str(message.tool_call_id or ""),
            }
        )
    return {"tool_results": results}


def _parse_tool_content(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(content)
    except (SyntaxError, ValueError):
        return content
