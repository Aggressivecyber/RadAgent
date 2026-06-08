"""Sensitive detector module agent — generates SensitiveDetector and Hit classes."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

SD_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 灵敏探测器模块编码 Agent。

你只负责以下 4 个文件，必须全部生成：
- include/SensitiveDetector.hh
- src/SensitiveDetector.cc
- include/Hit.hh
- src/Hit.cc

职责：
1. 实现 ProcessHits
2. 定义 Hit 类
3. 注册到 G4SDManager
4. 附加到 logical volume

严格要求：
1. 只生成 SensitiveDetector 和 Hit 相关文件
2. 不得实例化 G4VSensitiveDetector 抽象类
3. SensitiveDetector::AttachTo 如果存在，必须是非 static 成员函数；static 函数不能使用 this
4. 不要使用 SensitiveDetectorName；HitsCollection 构造时使用 GetName() 或显式 name
5. Hit 必须包含 trackID 字段，并提供 SetTrackID/GetTrackID
6. ProcessHits 必须调用 hit->SetTrackID(aStep->GetTrack()->GetTrackID())
7. Hit.cc 如果使用 std::setw/std::setprecision/std::fixed，必须 include <iomanip>
8. SensitiveDetector.hh 使用 G4LogicalVolume 时必须 include 或 forward declare
9. SensitiveDetector 不直接依赖 OutputManager；不得 include OutputManager.hh
10. SensitiveDetector 不调用 OutputManager::Instance 或 OutputManager 方法
11. 输出模块通过后续 action/integration 层读取 hit/scoring 数据
12. Hit.cc 或 Hit.hh 只要使用 CLHEP::MeV、CLHEP::ns、MeV、ns、mm、cm、keV、GeV、Gy 等单位，
    对应文件必须 include "G4SystemOfUnits.hh"
13. SensitiveDetector 构造函数中注册 hits collection 时必须使用 collectionName.push_back(GetName())
    或 collectionName.push_back("<collection_name>")；不要调用 collectionName.insert(...)
14. SensitiveDetector.cc 或 .hh 只要使用 G4THitsCollection<Hit>，
    对应文件必须 include "G4THitsCollection.hh"
15. SensitiveDetector.cc 使用 step->GetTrack()、GetPreStepPoint()、GetPosition()、GetCurrentEvent()
    时必须 include 对应 Geant4 头文件，不能依赖隐式 include
16. 输出 JSON 格式
"""


async def run_sensitive_detector_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run sensitive detector module agent."""
    return await run_module_agent(
        module_name="sensitive_detector",
        module_context=module_context,
        system_prompt=SD_SYSTEM_PROMPT,
    )
