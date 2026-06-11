"""Central registry for tools available to RadAgent agents."""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool

from agent_core.agent_tools.orbit_radiation import orbit_radiation_ap8ae8_query


@dataclass(frozen=True)
class AgentToolRegistry:
    """Named registry of tools that can be exposed to agent loops."""

    tools: tuple[BaseTool, ...]

    def all(self) -> list[BaseTool]:
        return list(self.tools)

    def get(self, name: str) -> BaseTool:
        for item in self.tools:
            if item.name == name:
                return item
        raise KeyError(f"unknown agent tool: {name}")


def get_agent_tool_registry() -> AgentToolRegistry:
    """Return the default RadAgent agent-tool registry."""
    return AgentToolRegistry(
        tools=(
            orbit_radiation_ap8ae8_query,
        )
    )
