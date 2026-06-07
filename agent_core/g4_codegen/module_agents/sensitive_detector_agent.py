"""Sensitive detector module agent — generates SensitiveDetector and Hit classes."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

SD_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 灵敏探测器模块编码 Agent。

你只负责 SensitiveDetector.hh/cc 和 Hit.hh/cc。

职责：
1. 实现 ProcessHits
2. 定义 Hit 类
3. 注册到 G4SDManager
4. 附加到 logical volume

严格要求：
1. 只生成 SensitiveDetector 和 Hit 相关文件
2. 不得实例化 G4VSensitiveDetector 抽象类
3. 输出 JSON 格式
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
