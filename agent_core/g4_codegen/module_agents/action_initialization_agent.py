"""Action initialization module agent — generates action classes."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

ACTION_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 动作初始化模块编码 Agent。

你负责：
1. ActionInitialization.hh/cc
2. RunAction.hh/cc
3. EventAction.hh/cc
4. SteppingAction.hh/cc

职责：
1. 初始化所有 user actions
2. 连接 RunAction、EventAction、SteppingAction
3. 接入 PrimaryGeneratorAction
4. 接入 OutputManager

严格要求：
1. 只生成 ActionInitialization 及相关 action 文件
2. 使用 OutputManager 的稳定接口，且只能调用：
   OutputManager::Instance()->BeginRun(const G4Run*)
   OutputManager::Instance()->EndRun(const G4Run*)
   OutputManager::Instance()->BeginEvent(const G4Event*)
   OutputManager::Instance()->EndEvent(const G4Event*)
   OutputManager::Instance()->RecordStep(const G4Step*)
   OutputManager::Instance()->WriteEvent(const G4Event*)
3. 不得调用 BeginOfRun、EndOfRun、BeginOfEvent、EndOfEvent、RecordEventData 等非稳定接口
4. 输出 JSON 格式
"""


async def run_action_initialization_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run action initialization module agent."""
    return await run_module_agent(
        module_name="action_initialization",
        module_context=module_context,
        system_prompt=ACTION_SYSTEM_PROMPT,
    )
