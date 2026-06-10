"""LLM physics quality reviewer for generated Geant4 projects."""

from __future__ import annotations

import json
from typing import Any

from agent_core.models.gateway import _safe_parse_json, get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import STAGE_CODEGEN

MAX_REVIEW_CONTEXT_CHARS = 70_000

PHYSICS_REVIEW_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 物理质量审核 Agent。

你不写代码。你负责审核最终 Geant4 工程是否忠实满足原始 G4ModelIR 和用户需求。
重点关注：
1. 物理模型/physics list 是否适合粒子、能量、材料和 scoring 目标。
2. 粒子源是否忠实保留粒子类型、能量、方向、位置、空间分布和单位。
3. 几何、材料、敏感体和 scoring 是否被擅自简化。
4. transport precision 是否足够，包括 production cuts、range cuts、step limits、
   user limits、最小步长或等效控制是否合理。
5. 输出 artifact 是否代表真实 event/scoring 数据，而不是表头、固定零值或 fallback 假数据。
6. 如果使用 Geant4 示例代码，是否只是参考真实接口，而不是把 B1/B2 示例需求照搬进当前需求。

只返回 JSON，不要输出 Markdown fence。

返回格式：
{
  "status": "pass" | "revise" | "fail",
  "overall_score": 0,
  "physics_model_score": 0,
  "source_fidelity_score": 0,
  "geometry_fidelity_score": 0,
  "transport_precision_score": 0,
  "output_validity_score": 0,
  "findings": [{"severity": "low|medium|high", "target": "...", "message": "..."}],
  "required_fixes": [{"target": "...", "message": "..."}],
  "reviewer_notes": "..."
}
"""


async def run_physics_quality_reviewer(
    *,
    proposed_patch: dict[str, Any],
    g4_model_ir: dict[str, Any],
    module_contracts: dict[str, Any],
    module_contexts: dict[str, Any],
    global_integration_report: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Review generated Geant4 physics/modeling fidelity with an LLM."""
    context = {
        "job_id": job_id,
        "g4_model_ir": _trim_json_value(g4_model_ir, max_chars=18_000),
        "module_contracts": _compact_module_contracts(module_contracts),
        "module_context_summaries": _compact_module_contexts(module_contexts),
        "global_integration_report": _trim_json_value(
            global_integration_report,
            max_chars=18_000,
        ),
        "project_files": _project_files_for_review(proposed_patch, max_total_chars=36_000),
        "review_instruction": (
            "Score physics/model/source/geometry/transport/output fidelity. "
            "When status is revise or fail, required_fixes must be concrete enough "
            "for global_integration_agent to patch the project."
        ),
    }
    prompt = json.dumps(context, indent=2, ensure_ascii=False)
    if len(prompt) > MAX_REVIEW_CONTEXT_CHARS:
        prompt = prompt[: MAX_REVIEW_CONTEXT_CHARS - 36] + "\n[truncated review context]"

    gateway = get_model_gateway()
    result = await gateway.call(
        task=ModelTask.FINAL_REVIEW,
        tier=ModelTier.MAX,
        system_prompt=PHYSICS_REVIEW_SYSTEM_PROMPT,
        user_prompt=prompt,
        response_format="json",
        max_tokens=8192,
        metadata={
            "job_id": job_id,
            "module_name": "physics_quality_reviewer",
            "enable_thinking": True,
        },
    )

    if result.error:
        review = {
            "status": "fail",
            "overall_score": 0,
            "errors": [f"Physics quality reviewer model call failed: {result.error}"],
            "required_fixes": [
                {
                    "target": "physics_quality_review",
                    "message": (
                        "Reviewer model call failed; generated physics fidelity "
                        "was not verified."
                    ),
                }
            ],
        }
        _persist_review(review, job_id)
        return review

    data = result.parsed_json or _safe_parse_json(result.content) or {}
    review = _normalize_review(data)
    _persist_review(review, job_id)
    return review


def physics_review_to_runtime_observation(review: dict[str, Any]) -> dict[str, Any]:
    """Convert revise/fail review output into global integration observation."""
    required_fixes = review.get("required_fixes", [])
    errors: list[str] = []
    if isinstance(required_fixes, list):
        for fix in required_fixes:
            if isinstance(fix, dict):
                target = fix.get("target", "physics_review")
                message = fix.get("message", "")
                errors.append(f"{target}: {message}")
    if not errors:
        errors = ["Physics quality reviewer requested revision without concrete fixes"]
    return {
        "status": "fail",
        "phase": "physics_quality_review",
        "errors": errors,
        "details": {
            "physics_quality_review": review,
            "failed_gates": [
                {
                    "gate_id": "physics_quality_review",
                    "name": "LLM physics fidelity review",
                    "status": review.get("status", "fail"),
                    "failed_items": errors,
                    "message": "Physics reviewer found modeling fidelity issues.",
                }
            ],
        },
    }


def _normalize_review(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    status = str(data.get("status", "fail")).strip().lower()
    if status not in {"pass", "revise", "fail"}:
        status = "fail"
    review: dict[str, Any] = {
        "status": status,
        "overall_score": _score(data.get("overall_score")),
        "physics_model_score": _score(data.get("physics_model_score")),
        "source_fidelity_score": _score(data.get("source_fidelity_score")),
        "geometry_fidelity_score": _score(data.get("geometry_fidelity_score")),
        "transport_precision_score": _score(data.get("transport_precision_score")),
        "output_validity_score": _score(data.get("output_validity_score")),
        "findings": _list_of_dicts(data.get("findings", [])),
        "required_fixes": _list_of_dicts(data.get("required_fixes", [])),
        "reviewer_notes": str(data.get("reviewer_notes", "")),
    }
    if status in {"revise", "fail"} and not review["required_fixes"]:
        review["required_fixes"] = [
            {
                "target": "physics_quality_review",
                "message": (
                    "Reviewer did not provide concrete fixes; rerun review or "
                    "inspect findings."
                ),
            }
        ]
    return review


def _score(value: Any) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(100, parsed))


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _project_files_for_review(
    proposed_patch: dict[str, Any],
    *,
    max_total_chars: int,
) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    used_chars = 0
    for item in proposed_patch.get("changed_files", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        content = str(item.get("new_content", ""))
        if not path or not content:
            continue
        remaining = max_total_chars - used_chars
        if remaining <= 0:
            break
        clipped = content[: min(len(content), remaining)]
        used_chars += len(clipped)
        files.append(
            {
                "path": path,
                "module_name": str(item.get("module_name", "")),
                "generated_by": str(item.get("generated_by", "")),
                "new_content": clipped,
            }
        )
    return files


def _compact_module_contracts(module_contracts: Any) -> dict[str, Any]:
    if not isinstance(module_contracts, dict):
        return {}
    compact: dict[str, Any] = {}
    for module_name, contract in module_contracts.items():
        if not isinstance(contract, dict):
            continue
        compact[str(module_name)] = {
            key: contract.get(key)
            for key in ("responsibilities", "output_files", "required_symbols", "dependencies")
            if contract.get(key) is not None
        }
    return compact


def _compact_module_contexts(module_contexts: Any) -> dict[str, Any]:
    if not isinstance(module_contexts, dict):
        return {}
    compact: dict[str, Any] = {}
    for module_name, context in module_contexts.items():
        if not isinstance(context, dict):
            continue
        compact[str(module_name)] = {
            "module_name": context.get("module_name"),
            "g4_model_ir_subset": _trim_json_value(
                context.get("g4_model_ir_subset", {}),
                max_chars=5000,
            ),
            "geant4_api_rules": context.get("geant4_api_rules", [])[:12],
            "example_lookup_used": bool(context.get("geant4_example_lookup_results")),
        }
    return compact


def _trim_json_value(value: Any, *, max_chars: int) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= max_chars:
        return value
    return {"summary": text[: max_chars - 32] + "\n[truncated for review]"}


def _persist_review(review: dict[str, Any], job_id: str) -> None:
    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)
    (codegen_dir / "physics_quality_review.json").write_text(
        json.dumps(review, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
