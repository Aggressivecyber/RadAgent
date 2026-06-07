"""Integration assembler — combines module outputs into proposed_patch."""

from __future__ import annotations

import json
from typing import Any


def assemble_proposed_patch(
    module_results: dict[str, dict[str, Any]],
    module_gate_results: dict[str, dict[str, Any]],
    job_id: str,
) -> dict[str, Any]:
    """Assemble proposed_patch from passed module results.

    Only includes files from modules that passed both hard and LLM gates.
    Output uses new_content field (never 'content').
    """
    changed_files: list[dict[str, Any]] = []
    module_gate_summary: dict[str, str] = {}
    passed_count = 0
    failed_count = 0
    agent_file_count = 0

    for module_name, result in module_results.items():
        # Check gate status
        gate_result = module_gate_results.get(module_name, {})
        hard_status = gate_result.get("hard", {}).get("status", "fail")
        llm_status = gate_result.get("llm", {}).get("status", "fail")

        if hard_status == "pass" and llm_status == "pass":
            module_gate_summary[module_name] = "pass"
            passed_count += 1
        else:
            module_gate_summary[module_name] = "fail"
            failed_count += 1
            continue

        # Include files from passed modules
        for f in result.get("generated_files", []):
            changed_files.append({
                "path": f["path"],
                "operation": f.get("operation", "create_or_replace"),
                "new_content": f["new_content"],
                "generated_by": f.get("generated_by", f"{module_name}_module_agent"),
                "module_name": f.get("module_name", module_name),
                "rationale": f.get("rationale", ""),
                "dependencies": f.get("dependencies", []),
                "satisfies": f.get("satisfies", []),
                "risk_notes": f.get("risk_notes", []),
                "used_references": f.get("used_references", []),
            })
            agent_file_count += 1

    patch = {
        "patch_type": "json_file_replacement",
        "changed_files": changed_files,
        "metadata": {
            "source": "g4_codegen_agent_modules",
            "module_agent_count": len(module_results),
            "passed_module_count": passed_count,
            "failed_module_count": failed_count,
            "agent_authored_file_count": agent_file_count,
            "module_gate_summary": module_gate_summary,
        },
    }

    # Persist
    from agent_core.config.workspace import get_job_dir
    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)

    patch_path = codegen_dir / "proposed_patch.json"
    patch_path.write_text(json.dumps(patch, indent=2, ensure_ascii=False))

    summary_path = codegen_dir / "proposed_patch_summary.json"
    summary = {
        "patch_type": patch["patch_type"],
        "total_files": len(changed_files),
        "metadata": patch["metadata"],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    return patch
