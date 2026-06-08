"""Module repair loop — attempts to fix failed modules."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.g4_codegen.schemas import ModuleAgentResult, ModuleGateResult
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier

logger = logging.getLogger(__name__)

MAX_REPAIR_ATTEMPTS = 3

REPAIR_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 模块修复 Agent。

当前模块的代码生成失败了。请根据以下信息修复代码：
1. 原始模块上下文
2. 失败的代码
3. 硬门禁失败原因
4. LLM 门禁失败原因
5. 静态扫描失败原因

要求：
1. 只修复当前模块的文件
2. 不要重新生成整个工程
3. 修复后的代码必须通过硬门禁
4. 输出 JSON 格式
"""


async def repair_module(
    module_name: str,
    module_context: dict[str, Any],
    original_result: ModuleAgentResult,
    gate_result: ModuleGateResult,
    max_attempts: int = MAX_REPAIR_ATTEMPTS,
) -> ModuleAgentResult:
    """Attempt to repair a failed module.

    Up to max_attempts repair iterations.
    Each iteration:
    1. Send failure info to repair agent
    2. Get repaired code
    3. Re-run hard gate
    4. If pass, return repaired result
    """
    from agent_core.g4_codegen.module_gates.hard_gate_base import run_hard_gate_checks

    attempts: list[dict[str, Any]] = []
    current_result = original_result

    for attempt in range(max_attempts):
        logger.info("Repair attempt %d/%d for %s", attempt + 1, max_attempts, module_name)

        # Build repair context
        repair_context = {
            "module_name": module_name,
            "module_context": module_context,
            "previous_errors": current_result.errors,
            "gate_errors": gate_result.errors,
            "gate_warnings": gate_result.warnings,
            "attempt": attempt + 1,
            "max_attempts": max_attempts,
        }

        # Call repair agent
        gateway = get_model_gateway()
        result = await gateway.call(
            task=ModelTask.FAILURE_DIAGNOSIS,
            tier=ModelTier.MAX,
            system_prompt=REPAIR_SYSTEM_PROMPT,
            user_prompt=f"修复上下文：\n{json.dumps(repair_context, indent=2, ensure_ascii=False)[:4000]}",  # noqa: E501
            response_format="json",
            max_tokens=65536,
            metadata={"module_name": module_name, "repair_attempt": attempt + 1},
        )

        if result.error:
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": f"Repair call failed: {result.error}",
                }
            )
            continue

        # Parse repair result
        try:
            data = result.parsed_json or json.loads(result.content.strip())
        except (json.JSONDecodeError, TypeError) as exc:
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": f"Invalid JSON: {exc}",
                }
            )
            continue

        # Build repaired result
        from agent_core.g4_codegen.schemas import GeneratedModuleFile

        repaired_files: list[GeneratedModuleFile] = []
        for f in data.get("generated_files", []):
            try:
                repaired_files.append(
                    GeneratedModuleFile(
                        path=f["path"],
                        operation=f.get("operation", "create_or_replace"),
                        new_content=f["new_content"],
                        generated_by=f.get("generated_by", f"{module_name}_module_agent"),
                        module_name=f.get("module_name", module_name),
                        rationale=f.get("rationale", "repaired"),
                        dependencies=f.get("dependencies", []),
                        satisfies=f.get("satisfies", []),
                        risk_notes=f.get("risk_notes", []),
                        used_references=f.get("used_references", []),
                    )
                )
            except (KeyError, TypeError):
                pass

        if not repaired_files:
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "status": "failed",
                    "error": "No valid files in repair response",
                }
            )
            continue

        repaired_result = ModuleAgentResult(
            module_name=module_name,
            status="repaired",
            generated_files=repaired_files,
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
        )

        # Re-run hard gate
        gate = run_hard_gate_checks(module_name, repaired_files)
        attempts.append(
            {
                "attempt": attempt + 1,
                "status": "repaired",
                "gate_status": gate.status,
            }
        )

        if gate.status == "pass":
            logger.info("Module %s repaired successfully on attempt %d", module_name, attempt + 1)
            return repaired_result

        current_result = repaired_result
        gate_result = gate

    # All attempts failed
    logger.warning("Module %s repair failed after %d attempts", module_name, max_attempts)
    return ModuleAgentResult(
        module_name=module_name,
        status="failed",
        generated_files=current_result.generated_files,
        repair_attempts=attempts,
        errors=[f"Repair failed after {max_attempts} attempts"] + current_result.errors,
    )


def save_repair_summary(
    module_name: str,
    result: ModuleAgentResult,
    job_id: str,
) -> None:
    """Save repair summary to disk."""
    from agent_core.config.workspace import get_job_dir

    repair_dir = get_job_dir(job_id) / "06_codegen" / "repair"
    repair_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "module_name": module_name,
        "status": result.status,
        "repair_attempts": result.repair_attempts,
        "errors": result.errors,
    }

    path = repair_dir / f"{module_name}_repair_summary.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
