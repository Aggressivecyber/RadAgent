"""Main/CMake module agent — generates main.cc, CMakeLists.txt, macros."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

MAIN_CMAKE_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 主程序/CMake 模块编码 Agent。

你负责：
1. main.cc
2. CMakeLists.txt
3. run.mac
4. init.mac

职责：
1. 生成 main.cc 入口
2. 生成 CMakeLists.txt 构建配置
3. 生成运行宏文件
4. 目录结构

严格要求：
1. 只生成 main.cc、CMakeLists.txt 和宏文件
2. CMakeLists.txt 必须包含所有 src/*.cc
3. 输出 JSON 格式
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
