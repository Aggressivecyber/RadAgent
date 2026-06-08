"""Main/CMake module agent — generates main.cc, CMakeLists.txt, macros."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

MAIN_CMAKE_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 主程序/CMake 模块编码 Agent。

你负责：
1. main.cc
2. CMakeLists.txt
3. macros/run.mac
4. macros/init.mac

职责：
1. 生成 main.cc 入口
2. 生成 CMakeLists.txt 构建配置
3. 生成运行宏文件
4. 目录结构

严格要求：
1. 只生成 main.cc、CMakeLists.txt、macros/run.mac、macros/init.mac
2. CMakeLists.txt 必须显式列出 main.cc 和所有已生成的 src/*.cc，不得使用 file(GLOB)
   main.cc 位于 08_geant4 根目录，CMake 中必须写 main.cc，不得写 src/main.cc
   不要在注释里写 file(GLOB) 这种禁用模式文本
3. main.cc 必须使用前序模块实际生成的 physics 类名/头文件
4. 如果 init.mac 包含 /run/initialize，main.cc 不得再调用 runManager->Initialize()
5. main.cc 的交互模式执行 macros/init.mac，批处理模式执行用户传入的 macro
6. 不得生成顶层 run.mac 或 init.mac；宏文件路径必须带 macros/ 前缀
7. main.cc 实例化 PhysicsListFactoryWrapper 时必须匹配 physics 模块真实声明；
   如果 PhysicsListFactoryWrapper.hh 只有默认构造函数，就先创建 wrapper 对象，
   再调用 wrapper->CreatePhysicsList()，把返回的 G4VUserPhysicsList* 传给
   runManager->SetUserInitialization(...)
   不得把 PhysicsListFactoryWrapper* 本身传给 SetUserInitialization
   不得调用 new PhysicsListFactoryWrapper("FTFP_BERT")
8. 输出 JSON 格式
"""


async def run_main_cmake_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run main/CMake module agent."""
    return await run_module_agent(
        module_name="main_cmake",
        module_context=module_context,
        system_prompt=MAIN_CMAKE_SYSTEM_PROMPT,
    )
