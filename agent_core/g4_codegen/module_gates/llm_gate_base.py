"""Base class for module LLM gates — semantic checks via ModelGateway."""

from __future__ import annotations

import json
from typing import Any

from agent_core.g4_codegen.schemas import ModuleGateResult
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier

MODULE_LLM_GATE_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 模块审查 Agent。
你只审查当前模块，不审查整个工程。

请根据 ModuleContract、ModuleContext、G4ModelIR 子集、
生成文件内容、硬门禁结果，
判断当前模块是否可以进入集成阶段。

你必须检查：
1. 是否忠于 G4ModelIR；
2. 是否存在未批准简化；
3. 是否存在职责越界；
4. 是否存在与其他模块接口不清；
5. 是否存在明显 Geant4 API 错误；
6. 是否存在物理建模风险；
7. 是否需要 human confirmation；
8. 是否可以进入 integration。

返回 JSON：
{
  "status": "pass | fail",
  "module_name": "...",
  "semantic_checks": [],
  "risks": [],
  "required_fixes": [],
  "requires_human_confirmation": false,
  "reviewer_notes": "..."
}
"""


async def run_llm_gate(
    module_name: str,
    module_context: dict[str, Any],
    generated_files_content: list[dict[str, Any]],
    hard_gate_result: dict[str, Any],
) -> ModuleGateResult:
    """Run LLM gate for a module.

    Only runs if hard gate passed.
    Uses ModelGateway with GATE_EXPLANATION task and MAX tier.
    """
    # Check hard gate status
    if hard_gate_result.get("status") == "fail":
        return ModuleGateResult(
            module_name=module_name,
            gate_type="llm",
            status="skipped",
            checks=[],
            errors=["Hard gate failed — LLM gate skipped"],
        )

    gateway = get_model_gateway()

    user_prompt = f"""模块名称：{module_name}

模块上下文：
{json.dumps(module_context, indent=2, ensure_ascii=False)[:3000]}

生成文件内容摘要：
{json.dumps(generated_files_content, indent=2, ensure_ascii=False)[:3000]}

硬门禁结果：
{json.dumps(hard_gate_result, indent=2, ensure_ascii=False)[:1000]}

请判断当前模块是否可以进入集成阶段。返回 JSON。"""

    result = await gateway.call(
        task=ModelTask.GATE_EXPLANATION,
        tier=ModelTier.MAX,
        system_prompt=MODULE_LLM_GATE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_format="json",
        max_tokens=4096,
        metadata={"module_name": module_name},
    )

    if result.error:
        return ModuleGateResult(
            module_name=module_name,
            gate_type="llm",
            status="fail",
            checks=[],
            errors=[f"LLM gate call failed: {result.error}"],
        )

    try:
        data = result.parsed_json or json.loads(result.content.strip())
    except (json.JSONDecodeError, TypeError):
        return ModuleGateResult(
            module_name=module_name,
            gate_type="llm",
            status="fail",
            checks=[],
            errors=["Invalid JSON from LLM gate"],
        )

    return ModuleGateResult(
        module_name=module_name,
        gate_type="llm",
        status=data.get("status", "fail"),
        checks=data.get("semantic_checks", []),
        errors=data.get("required_fixes", []),
        warnings=data.get("risks", []),
        reviewer_notes=data.get("reviewer_notes"),
    )
