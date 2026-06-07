"""Source module agent — generates PrimaryGeneratorAction.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

SOURCE_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 源项模块编码 Agent。

你只负责 PrimaryGeneratorAction.hh 和 PrimaryGeneratorAction.cc。

职责：
1. 配置 particle gun 或 GPS
2. 设置粒子类型、能量、方向
3. 处理多源（如需要）

严格要求：
1. 只生成 PrimaryGeneratorAction 相关文件
2. 不得生成 geometry、physics 等
3. 输出 JSON 格式
"""


async def run_source_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run source module agent."""
    return await run_module_agent(
        module_name="source",
        module_context=module_context,
        system_prompt=SOURCE_SYSTEM_PROMPT,
    )
