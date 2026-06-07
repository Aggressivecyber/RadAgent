"""Material module agent — generates MaterialRegistry.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

MATERIAL_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 材料模块编码 Agent。

你只负责 MaterialRegistry.hh 和 MaterialRegistry.cc。

职责：
1. 使用 G4NistManager 获取 NIST 材料
2. 定义自定义材料（如需要）
3. 提供按名称查找材料的接口
4. 材料名称映射

严格要求：
1. 只生成 MaterialRegistry.hh 和 MaterialRegistry.cc
2. 不得生成 geometry、source、physics 等其他模块代码
3. 使用 G4SystemOfUnits.hh 中的单位
4. 不得输出 Markdown fence
5. 不得出现 TODO/NotImplemented/stub
6. 输出 JSON 格式
"""


async def run_material_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run material module agent."""
    result = await run_module_agent(
        module_name="material",
        module_context=module_context,
        system_prompt=MATERIAL_SYSTEM_PROMPT,
    )
    return result
