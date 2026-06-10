"""Beam and physics agent — generates source and physics list files."""

from __future__ import annotations

from typing import Any

from agent_core.g4_codegen.module_agents.base import run_module_agent
from agent_core.g4_codegen.schemas import ModuleAgentResult

BEAM_PHYSICS_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 beam_physics 编码 Agent。

你负责一次性生成 PrimaryGeneratorAction、PhysicsListFactoryWrapper 和 physics_list.mac。
目标是保证粒子源、物理列表、production cuts/range cuts 和传输精度策略与原始需求一致。

必须生成 module_contract.output_files 中列出的完整文件内容。

质量要求：
1. 粒子类型、能量、位置、方向、空间/角分布必须来自 G4ModelIR sources，不得擅自改默认值。
2. 如果 G4ModelIR sources 包含多个 source，必须实现 all sources 的 multi-source 生成逻辑；
   不能只使用第一个 source，且必须保留每个 source 的 spectrum、direction、angular_distribution、
   events 和 relative_weight 语义。
3. 物理列表必须与全部粒子、能量范围、材料和 scoring 目的匹配，并在 rationale 中说明选择原因。
4. 对剂量/能量沉积或小尺寸探测器场景，必须考虑 production cuts、range cuts、step limiter
   或用户 limits；如果不需要，也要在 risk_notes 中解释。
5. 使用 G4SystemOfUnits.hh 中的单位常量，保持 IR global_units 的语义。
6. 只返回 JSON，不得输出 Markdown fence。
"""


async def run_beam_physics_agent(
    module_context: dict[str, Any],
) -> ModuleAgentResult:
    """Run the coarse beam and physics module agent."""
    return await run_module_agent(
        module_name="beam_physics",
        module_context=module_context,
        system_prompt=BEAM_PHYSICS_SYSTEM_PROMPT,
    )
