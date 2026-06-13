"""Integration assembler — combines module outputs into proposed_patch."""

from __future__ import annotations

import json
from typing import Any

from agent_core.workspace.paths import STAGE_CODEGEN


def assemble_proposed_patch(
    module_results: dict[str, dict[str, Any]],
    job_id: str,
) -> dict[str, Any]:
    """Assemble proposed_patch from generated module results.

    The final integration agent owns compile/runtime repair from real
    observations, so the assembler forwards every file produced by a
    generated/repaired coarse module.
    Output uses new_content field (never 'content').
    """
    changed_files: list[dict[str, Any]] = []
    included_count = 0
    failed_count = 0
    agent_file_count = 0

    for module_name, result in module_results.items():
        if result.get("status") not in {"generated", "repaired"}:
            failed_count += 1
            continue
        included_count += 1

        for f in result.get("generated_files", []):
            raw_path = f["path"]
            # Security: reject path traversal
            if ".." in raw_path or raw_path.startswith("/"):
                continue
            # Strip any leading directory prefix so path is relative to geant4_project
            clean_path = raw_path.lstrip("/")
            if clean_path.startswith("geant4_project/"):
                clean_path = clean_path[len("geant4_project/") :]
            elif clean_path.startswith("geant4_project"):
                clean_path = clean_path[len("geant4_project") :].lstrip("/")

            changed_files.append(
                {
                    "path": clean_path,
                    "operation": f.get("operation", "create"),
                    "new_content": f["new_content"],
                    "zone": "green",
                    "generated_by": f.get("generated_by", f"{module_name}_module_agent"),
                    "module_name": f.get("module_name", module_name),
                    "rationale": f.get("rationale", ""),
                    "dependencies": f.get("dependencies", []),
                    "satisfies": f.get("satisfies", []),
                    "risk_notes": f.get("risk_notes", []),
                    "used_references": f.get("used_references", []),
                }
            )
            agent_file_count += 1

    # Force the canonical CMakeLists.txt (Geant4 B1 template that file(GLOB)s
    # every src/*.cc + include/*.hh). CMake is formulaic and the model
    # reinventing it per run was a recurring source of build failures; the
    # glob template needs no per-project editing, so the canonical version
    # always wins regardless of what the runtime_app agent emitted.
    from agent_core.g4_codegen.cmake_template import CMAKE_PATH, RADAGENT_CMAKE_TEMPLATE

    changed_files = [c for c in changed_files if c.get("path") != CMAKE_PATH]
    changed_files.append(
        {
            "path": CMAKE_PATH,
            "operation": "create_or_replace",
            "new_content": RADAGENT_CMAKE_TEMPLATE,
            "zone": "green",
            "generated_by": "canonical_cmake_template",
            "module_name": "runtime_app",
            "rationale": "Fixed B1-derived CMake (ui_all vis_all + file(GLOB sources))",
            "dependencies": [],
            "satisfies": [],
            "risk_notes": [],
            "used_references": [],
        }
    )

    patch = {
        "patch_id": f"patch_{job_id}_g4_codegen",
        "job_id": job_id,
        "description": "Agent-generated Geant4 project files from module-level codegen",
        "change_type": "create_or_replace",
        "risk_level": "medium",
        "patch_type": "json_file_replacement",
        "changed_files": changed_files,
        "test_plan": [
            "Verify all generated files compile with Geant4 toolchain",
            "Run dry-run simulation to confirm geometry/material setup",
        ],
        "expected_outputs": [
            "All files written to geant4_project directory",
            "No compilation errors in generated C++ code",
        ],
        "metadata": {
            "source": "g4_codegen_agent_modules",
            "module_agent_count": len(module_results),
            "included_module_count": included_count,
            "passed_module_count": included_count,
            "failed_module_count": failed_count,
            "agent_authored_file_count": agent_file_count,
        },
    }

    # Persist
    from agent_core.workspace.io import get_job_dir

    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
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
