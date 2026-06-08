"""Geometry module agent — generates DetectorConstruction.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

GEOMETRY_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 几何模块编码 Agent。

你只负责 DetectorConstruction.hh 和 DetectorConstruction.cc。

职责：
1. 定义 world volume
2. 创建 solids（G4Box, G4Tubs 等）
3. 创建 logical volumes
4. 构建组件层次结构
5. 为需要跨模块使用的 logical volume 提供 getter 或成员引用

严格要求：
1. 只生成 DetectorConstruction.hh 和 DetectorConstruction.cc
2. 不得生成 particle source、physics list、output manager 等
3. 不得把 CAD/GDML 转换成 G4Box
4. 不得伪造 CAD 转换
5. 不得 include SensitiveDetector.hh
6. 不得实例化 SensitiveDetector 或 G4VSensitiveDetector
7. 不得在 geometry 模块调用 SetSensitiveDetector；灵敏探测器模块负责 SD 创建/注册/附加
8. 材料查找必须使用 MaterialRegistry 提供的真实接口。优先使用构造函数传入的
   MaterialRegistry* 成员；如果调用 MaterialRegistry::GetInstance()，material 模块
   必须真实提供该 static 方法。
9. 输出 JSON 格式
"""


async def run_geometry_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run geometry module agent."""
    return await run_module_agent(
        module_name="geometry",
        module_context=module_context,
        system_prompt=GEOMETRY_SYSTEM_PROMPT,
    )
