"""Physics module agent — generates PhysicsListFactoryWrapper.hh/cc."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

PHYSICS_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 物理模块编码 Agent。

你只负责 PhysicsListFactoryWrapper.hh、PhysicsListFactoryWrapper.cc 和 physics 宏文件。

职责：
1. 注册 physics list
2. 配置 EM/hadronic 过程
3. 设置 production cuts

严格要求：
1. 只生成 PhysicsListFactoryWrapper 相关文件
2. 不得生成 geometry、source 等
3. 头文件中如果默认参数或声明使用 mm、cm、MeV、keV 等 Geant4 单位，必须 include G4SystemOfUnits.hh
4. 使用 G4PhysListFactory::GetReferencePhysList 创建参考 physics list
5. PhysicsListFactoryWrapper 不得 delete fPhysicsList；
   physics list 指针会交给 Geant4 run manager 生命周期管理
6. destructor 必须为空或 defaulted
7. 输出 JSON 格式
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
