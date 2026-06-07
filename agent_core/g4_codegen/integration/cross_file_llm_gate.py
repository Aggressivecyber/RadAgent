"""Cross-file LLM gate — semantic consistency check across all modules."""

from __future__ import annotations

import json
from typing import Any

from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier

CROSS_FILE_LLM_GATE_PROMPT = """你是 RadAgent 的 Geant4 全工程审查 Agent。

请审查整个 Geant4 工程的语义一致性。

检查：
1. 模块之间职责是否一致
2. G4 lifecycle 是否完整
3. source、physics、geometry、scoring 是否匹配
4. 是否存在未批准简化
5. 是否存在物理配置明显不合理
6. 是否存在 CAD/GDML 虚假实现
7. 是否存在 TCAD/SPICE 伪造
8. 是否需要 human confirmation
9. 是否可以进入 patch_subgraph

返回 JSON：
{
  "status": "pass | fail",
  "checks": [],
  "risks": [],
  "required_fixes": [],
  "requires_human_confirmation": false,
  "reviewer_notes": "..."
}
"""


async def run_cross_file_llm_gate(
    proposed_patch: dict[str, Any],
    module_gate_results: dict[str, dict[str, Any]],
    job_id: str,
) -> dict[str, Any]:
    """Run cross-file LLM gate.

    Only runs if cross-file hard gate passed.
    Uses ModelGateway with GATE_EXPLANATION task and MAX tier.
    """
    # Check cross-file hard gate
    from agent_core.config.workspace import get_job_dir
    hard_gate_path = get_job_dir(job_id) / "06_codegen" / "cross_file_hard_gate.json"
    if hard_gate_path.exists():
        hard_gate = json.loads(hard_gate_path.read_text())
        if hard_gate.get("status") == "fail":
            result = {
                "status": "skipped",
                "checks": [],
                "errors": ["Cross-file hard gate failed — LLM gate skipped"],
            }
            _persist_result(result, job_id)
            return result

    gateway = get_model_gateway()

    # Build summary for LLM
    file_summary = []
    for f in proposed_patch.get("changed_files", []):
        file_summary.append({
            "path": f["path"],
            "generated_by": f.get("generated_by", ""),
            "module_name": f.get("module_name", ""),
            "content_length": len(f.get("new_content", "")),
        })

    user_prompt = f"""文件摘要：
{json.dumps(file_summary, indent=2, ensure_ascii=False)}

模块门禁结果：
{json.dumps(module_gate_results, indent=2, ensure_ascii=False)[:2000]}

请审查全工程语义一致性。返回 JSON。"""

    result = await gateway.call(
        task=ModelTask.GATE_EXPLANATION,
        tier=ModelTier.MAX,
        system_prompt=CROSS_FILE_LLM_GATE_PROMPT,
        user_prompt=user_prompt,
        response_format="json",
        max_tokens=4096,
    )

    if result.error:
        gate_result = {
            "status": "fail",
            "checks": [],
            "errors": [f"LLM gate call failed: {result.error}"],
        }
        _persist_result(gate_result, job_id)
        return gate_result

    try:
        data = result.parsed_json or json.loads(result.content.strip())
    except (json.JSONDecodeError, TypeError):
        gate_result = {
            "status": "fail",
            "checks": [],
            "errors": ["Invalid JSON from LLM gate"],
        }
        _persist_result(gate_result, job_id)
        return gate_result

    gate_result = {
        "status": data.get("status", "fail"),
        "checks": data.get("checks", []),
        "errors": data.get("required_fixes", []),
        "warnings": data.get("risks", []),
        "reviewer_notes": data.get("reviewer_notes"),
    }

    _persist_result(gate_result, job_id)
    return gate_result


def _persist_result(result: dict[str, Any], job_id: str) -> None:
    """Persist cross-file LLM gate result."""
    from agent_core.config.workspace import get_job_dir
    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)

    gate_path = codegen_dir / "cross_file_llm_gate.json"
    gate_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
