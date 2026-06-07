"""Scoring module agent — generates ScoringManager.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

SCORING_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 计分模块编码 Agent。

你只负责 ScoringManager.hh 和 ScoringManager.cc。

职责：
1. 管理 dose/edep scoring
2. 配置 primitive scorers
3. 处理 mesh scoring
4. scoring 输出契约

严格要求：
1. 只生成 ScoringManager 相关文件
2. 输出 JSON 格式
"""


async def run_scoring_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run scoring module agent."""
    return await run_module_agent(
        module_name="scoring",
        module_context=module_context,
        system_prompt=SCORING_SYSTEM_PROMPT,
    )
