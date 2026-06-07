"""Physics module agent — generates PhysicsList.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

PHYSICS_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 物理模块编码 Agent。

你只负责 PhysicsList.hh 和 PhysicsList.cc。

职责：
1. 注册 physics list
2. 配置 EM/hadronic 过程
3. 设置 production cuts

严格要求：
1. 只生成 PhysicsList 相关文件
2. 不得生成 geometry、source 等
3. 输出 JSON 格式
"""


async def run_physics_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run physics module agent."""
    return await run_module_agent(
        module_name="physics",
        module_context=module_context,
        system_prompt=PHYSICS_SYSTEM_PROMPT,
    )
