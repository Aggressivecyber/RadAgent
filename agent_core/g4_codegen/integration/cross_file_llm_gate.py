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
    static_semantic_scan: dict[str, Any] | None = None,
    cross_file_hard_gate: dict[str, Any] | None = None,
    interface_contracts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run cross-file LLM gate.

    Only runs if cross-file hard gate passed.
    Uses ModelGateway with GATE_EXPLANATION task and MAX tier.
    """
    # Check cross-file hard gate
    from agent_core.config.workspace import get_job_dir as _get_job_dir
    hard_gate_path = _get_job_dir(job_id) / "06_codegen" / "cross_file_hard_gate.json"
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

    # ── Build code review bundle ─────────────────────────────────────
    # Read static scan and cross-file hard gate from disk if not provided
    codegen_dir = _get_job_dir(job_id) / "06_codegen"

    if static_semantic_scan is None:
        scan_path = codegen_dir / "static_semantic_scan.json"
        if scan_path.exists():
            static_semantic_scan = json.loads(scan_path.read_text())
        else:
            static_semantic_scan = {}

    if cross_file_hard_gate is None:
        hard_gate_path = codegen_dir / "cross_file_hard_gate.json"
        if hard_gate_path.exists():
            cross_file_hard_gate = json.loads(hard_gate_path.read_text())
        else:
            cross_file_hard_gate = {}

    code_review_bundle: dict[str, Any] = {
        "proposed_patch_metadata": {
            "patch_type": proposed_patch.get("patch_type", proposed_patch.get("change_type", "")),
            "total_files": len(proposed_patch.get("changed_files", [])),
        },
        "module_gate_summary": module_gate_results,
        "static_semantic_scan": static_semantic_scan,
        "cross_file_hard_gate": cross_file_hard_gate,
        "file_details": [],
        "g4_lifecycle_summary": (
            "Geant4 simulation lifecycle: detector construction "
            "→ physics list → primary generator → run manager "
            "→ sensitive detector → scoring → output"
        ),
        "interface_contracts": interface_contracts or {},
    }

    for f in proposed_patch.get("changed_files", []):
        code_review_bundle["file_details"].append({
            "path": f.get("path", ""),
            "module_name": f.get("module_name", ""),
            "generated_by": f.get("generated_by", ""),
            "includes": _extract_includes(f.get("new_content", "")),
            "classes": _extract_classes(f.get("new_content", "")),
            "public_methods": _extract_public_methods(f.get("new_content", "")),
            "content_excerpt": f.get("new_content", "")[:2000],
        })

    # ── Build LLM prompt ─────────────────────────────────────────────
    user_prompt = f"""代码审查包：
{json.dumps(code_review_bundle, indent=2, ensure_ascii=False)[:6000]}

请审查全工程语义一致性。返回 JSON。"""

    llm_result = await gateway.call(
        task=ModelTask.GATE_EXPLANATION,
        tier=ModelTier.MAX,
        system_prompt=CROSS_FILE_LLM_GATE_PROMPT,
        user_prompt=user_prompt,
        response_format="json",
        max_tokens=4096,
    )

    if llm_result.error:
        gate_result = {
            "status": "fail",
            "checks": [],
            "errors": [f"LLM gate call failed: {llm_result.error}"],
        }
        _persist_result(gate_result, job_id)
        return gate_result

    try:
        data = llm_result.parsed_json or json.loads(llm_result.content.strip())
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


# ── Helper functions for C++ parsing ─────────────────────────────────


def _extract_includes(content: str) -> list[str]:
    """Extract #include directives from C++ content."""
    import re
    return re.findall(r'#include\s+[<"]([^>"]+)[>"]', content)


def _extract_classes(content: str) -> list[str]:
    """Extract class names from C++ content."""
    import re
    return re.findall(r'\bclass\s+(\w+)', content)


def _extract_public_methods(content: str) -> list[str]:
    """Extract public method names from C++ content."""
    import re
    return re.findall(r'\bpublic:\s*(?:.*?)?\b(\w+)\s*\(', content, re.DOTALL)
