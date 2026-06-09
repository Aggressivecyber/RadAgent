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
7. production cuts 优先在 C++ SetCuts()/SetCutValue 中设置；
   宏文件中不要使用 /process/em/setCut ... proton 这类无效命令
   如果调用 SetDefaultCutValue，只能使用单参数形式：
   fPhysicsList->SetDefaultCutValue(0.7*mm);
   不要写 SetDefaultCutValue(value, "gamma")、SetDefaultCutValue(value, "e-")
   或其他双参数形式；Geant4 的 SetDefaultCutValue 不是按粒子名设置 cut 的 API。
8. 如果宏文件需要 cut 命令，只使用 Geant4 支持的 /run/setCut 或
   /run/setCutForAGivenParticle <particle> <value> <unit> 格式
9. 不要在 CreatePhysicsList() 函数体内创建局部 G4PhysListFactory factory 后直接返回
   factory.GetReferencePhysList(...) 的结果；把 G4PhysListFactory 作为
   PhysicsListFactoryWrapper 的成员变量，或使用 static/长生命周期 factory
10. 如果包装器缓存 fPhysicsList，CreatePhysicsList() 应重复返回同一指针，
    不要重复创建多个 physics list
11. 不要在生成代码或注释中写 "delete fPhysicsList" 这个文本；析构函数写成
    PhysicsListFactoryWrapper::~PhysicsListFactoryWrapper() = default; 或空函数体即可
12. physics_list.mac 必须只包含真实可执行的 Geant4 macro 命令或必要注释；
    不得出现 PLACEHOLDER、TODO、stub、dummy、NotImplemented 等占位词
13. 输出 JSON 格式
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
