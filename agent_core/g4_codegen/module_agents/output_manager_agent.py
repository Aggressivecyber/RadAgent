"""Output manager module agent — generates OutputManager.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

OUTPUT_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 输出管理模块编码 Agent。

你只负责 OutputManager.hh 和 OutputManager.cc。

职责：
1. 处理 CSV/JSON 输出
2. 管理 output package
3. 运行/事件摘要
4. 元数据管理

严格要求：
1. 只生成 OutputManager 相关文件
2. 输出 JSON 格式
"""


async def run_output_manager_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run output manager module agent."""
    return await run_module_agent(
        module_name="output_manager",
        module_context=module_context,
        system_prompt=OUTPUT_SYSTEM_PROMPT,
    )
