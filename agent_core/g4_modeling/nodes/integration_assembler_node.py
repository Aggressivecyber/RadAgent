"""Integration assembler node — collects code_modules into standard CodePatch.

Deterministic node: aggregates all codegen node outputs into a single
CodePatch that feeds into the existing review_code_patch → apply_patch
→ run_gate_checks pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_core.config.workspace import get_stage_dir
from agent_core.g4_codegen.schemas import G4CodegenSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def integration_assembler_node(state: RadiationAgentState) -> dict[str, Any]:
    """Assemble code_modules into a standard CodePatch.

    Reads: code_modules, g4_model_ir
    Writes: code_patch (standard field consumed by review_code_patch)
    """
    raw_code_modules = state.get("code_modules", [])
    code_modules: list[dict[str, Any]] = (
        raw_code_modules if isinstance(raw_code_modules, list) else []
    )
    model_ir_dict = state.get("g4_model_ir", {})
    job_id = state.get("job_id", "")

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Collect all generated files from codegen modules
    changed_files: list[dict[str, str]] = []
    module_summary: list[str] = []

    for mod in code_modules:
        module_name = mod.get("module_name", "unknown")
        module_type = mod.get("module_type", "unknown")
        source_files = mod.get("source_files", [])
        header_files = mod.get("header_files", [])
        config_files = mod.get("config_files", [])

        module_summary.append(
            f"  {module_name} ({module_type}): "
            f"{len(source_files)} src, {len(header_files)} hdr, "
            f"{len(config_files)} cfg"
        )

        # Each file needs path and new_content from the codegen node
        for files_list, prefix in [
            (source_files, "src"),
            (header_files, "include"),
            (config_files, "config"),
        ]:
            for f in files_list:
                file_key = f"{module_name}::{f}"
                content = mod.get("generated_content", {}).get(file_key, "")
                if content:
                    changed_files.append({
                        "path": f"{prefix}/{f}",
                        "operation": "create_or_replace",
                        "new_content": content,
                        "zone": "green",
                    })

    # Build the code patch compatible with CodePatch schema
    code_patch: dict[str, Any] = {
        "patch_type": "json_file_replacement",
        "patch_id": f"g4_complex_{model_ir.model_ir_id}",
        "job_id": job_id,
        "description": f"Geant4 complex model: {model_ir.model_ir_id}",
        "change_type": "create",
        "risk_level": "low",
        "changed_files": changed_files,
        "test_plan": ["compile_check"],
        "expected_outputs": [],
        "metadata": {
            "source": "g4_codegen_subgraph",
            "total_modules": len(code_modules),
            "total_files": len(changed_files),
            "module_summary": "\n".join(module_summary),
        },
    }

    model_ir.ledger.add_entry(
        node_name="integration_assembler_node",
        action="create",
        target_id="code_patch",
        description=f"Assembled {len(changed_files)} files from "
        f"{len(code_modules)} codegen modules",
        modified_fields=[],
    )

    # Persist assembled patch
    if job_id:
        model_ir_dir = get_stage_dir(job_id, "03_model_ir")
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        patch_file = model_ir_dir / "assembled_code_patch.json"
        patch_file.write_text(json.dumps(
            code_patch, indent=2, ensure_ascii=False,
        ))

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "code_patch": code_patch,
        "current_node": "integration_assembler_node",
    }
