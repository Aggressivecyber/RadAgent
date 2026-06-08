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
3. CSV header 必须稳定，事件行必须严格按 header 顺序写入
4. 对当前 IR，CSV 至少包含 EventID,edep_MeV,dose_Gy
5. 不得通过直接遍历 std::map/std::unordered_map 来写固定 CSV 列
6. 如果提供 RecordEventData(map)，必须显式按 edep_MeV、dose_Gy 的顺序读取 key
7. OutputManager.hh 必须声明以下稳定接口，供 action_initialization 模块调用：
   static OutputManager* Instance();
   void BeginRun(const G4Run* run);
   void EndRun(const G4Run* run);
   void BeginEvent(const G4Event* event);
   void EndEvent(const G4Event* event);
   void RecordStep(const G4Step* step);
   void WriteEvent(const G4Event* event);
8. OutputManager.hh 必须声明运行摘要和元数据接口：
   void SetRunMetadata(const std::string& key, const std::string& value);
   void WriteRunSummary();
   void WriteMetadata();
9. OutputManager.cc 必须实现运行摘要和元数据管理：
   BeginRun/EndRun 更新 run-level counters 或调用 WriteRunSummary/WriteMetadata
   SetRunMetadata 存储 simulation configuration、material info、physics list、job id 等键值
10. OutputManager.hh 必须 forward declare G4Run、G4Event、G4Step，或 include 对应 Geant4 头文件
11. OutputManager.cc 必须实现上述所有稳定接口
12. OutputManager 不直接依赖 ScoringManager；不得 include ScoringManager.hh
13. OutputManager 不调用 ScoringManager::Instance、GetEdepMeV、GetDoseGy 等方法
14. scoring 数据通过 RecordEventData 参数或 action 层传入，OutputManager 只负责写出
15. 不得出现 placeholder、TODO、dummy、stub、NotImplemented 等占位实现或占位注释
16. OutputManager.hh 只要声明 G4String 成员或参数，必须 include "G4String.hh"，
    不要依赖 G4Types.hh 或其他头文件的隐式包含
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
