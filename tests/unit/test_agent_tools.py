from __future__ import annotations

from agent_core.agent_tools.executor import execute_selected_agent_tools
from agent_core.agent_tools.graph import build_agent_tool_graph
from agent_core.agent_tools.registry import get_agent_tool_registry
from agent_core.agent_tools.selection import select_agent_tool_calls
from langchain_core.messages import ToolMessage


def test_orbit_radiation_tool_is_registered_for_copliot() -> None:
    registry = get_agent_tool_registry()

    tool = registry.get("orbit_radiation_ap8ae8_query")

    assert tool.name == "orbit_radiation_ap8ae8_query"
    assert "AP8" in tool.description
    assert "AE8" in tool.description


def test_orbit_radiation_question_selects_tool_call() -> None:
    calls = select_agent_tool_calls("查询 AP8 质子 solar min L=2.0 B/B0=1.05 的轨道辐照")

    assert len(calls) == 1
    assert calls[0]["name"] == "orbit_radiation_ap8ae8_query"
    assert calls[0]["args"] == {
        "message": "查询 AP8 质子 solar min L=2.0 B/B0=1.05 的轨道辐照"
    }
    assert calls[0]["id"].startswith("orbit_radiation_ap8ae8_query:")


def test_plain_beam_question_does_not_select_orbit_tool() -> None:
    assert select_agent_tool_calls("simulate a 10 MeV proton beam on silicon") == []


def test_agent_tool_graph_executes_orbit_radiation_tool() -> None:
    graph = build_agent_tool_graph().compile()

    result = graph.invoke(
        {
            "user_message": "查询 AP8 质子 solar min L=2.0 B/B0=1.05 的轨道辐照",
        }
    )

    messages = result["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], ToolMessage)
    assert messages[0].name == "orbit_radiation_ap8ae8_query"
    assert "AP8MIN" in messages[0].content
    assert result["tool_results"][0]["tool"] == "orbit_radiation_ap8ae8_query"
    assert result["tool_results"][0]["success"] is True
    assert result["tool_results"][0]["payload"]["ready"] is True
    assert result["tool_results"][0]["payload"]["model"] == "AP8MIN"


def test_direct_agent_tool_executor_uses_same_orbit_tool_contract() -> None:
    result = execute_selected_agent_tools(
        "查询 AP8 质子 solar min L=2.0 B/B0=1.05 的轨道辐照"
    )

    assert result[0]["tool"] == "orbit_radiation_ap8ae8_query"
    assert result[0]["success"] is True
    assert result[0]["payload"]["ready"] is True
    assert result[0]["payload"]["model"] == "AP8MIN"
