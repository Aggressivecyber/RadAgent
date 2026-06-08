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
6. 必须支持自定义材料定义，至少提供 AddCustomMaterial 或 RegisterCustomMaterial 接口，
   能把调用方提供/创建的 G4Material* 注册进内部名称映射
7. Initialize 必须同时注册 IR 中的 NIST 材料和自定义材料名称；找不到材料时要显式处理，
   不得静默 skip，也不得写 "for now"、"should handle" 这类占位注释
8. GetMaterial 不得只返回 nullptr；找不到材料时应先尝试 G4NistManager::FindOrBuildMaterial，
   仍失败时抛出异常或返回明确失败路径
9. 输出 JSON 格式
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
