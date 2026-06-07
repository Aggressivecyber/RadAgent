"""Artifact Subgraph nodes — collect GitHub-reviewable artifacts.

Only collects summaries, never full simulation_workspace/jobs or
large simulation output files.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from agent_core.artifacts.schemas import ArtifactSubgraphState


async def collect_artifacts(state: ArtifactSubgraphState) -> dict[str, Any]:
    """Collect review artifacts from all pipeline stages."""
    _job_id = state.get("job_id", "unknown")  # noqa: F841 — used by downstream nodes

    # Target: review_artifacts/g4_complex_model/latest/
    project_root = Path(__file__).resolve().parent.parent.parent
    artifact_dir = project_root / "review_artifacts" / "g4_complex_model" / "latest"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_dir = artifact_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    # Copy gate results
    gate_path = state.get("gate_results_path", "")
    if gate_path and Path(gate_path).exists():
        shutil.copy2(Path(gate_path), output_dir / "gate_results.json")

    # Copy model IR
    ir_path = state.get("g4_model_ir_path", "")
    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text())
        # Save full IR
        shutil.copy2(Path(ir_path), output_dir / "g4_model_ir.json")
        # Save component specs summary (lighter)
        components = model_ir.get("components", [])
        summary = {
            "total_components": len(components),
            "component_ids": [c.get("component_id", "?") for c in components],
            "materials_count": len(model_ir.get("materials", [])),
            "sources_count": len(model_ir.get("sources", [])),
            "scoring_count": len(model_ir.get("scoring", [])),
        }
        (output_dir / "component_specs_summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False)
        )

    # Copy model review report
    review_path = state.get("model_review_report_path", "")
    if review_path and Path(review_path).exists():
        shutil.copy2(Path(review_path), output_dir / "model_review_report.md")

    # Copy construction ledger
    ledger_path = state.get("construction_ledger_path", "")
    if ledger_path and Path(ledger_path).exists():
        shutil.copy2(Path(ledger_path), output_dir / "construction_ledger.json")

    # Copy code module plan
    plan_path = state.get("code_module_plan_path", "")
    if plan_path and Path(plan_path).exists():
        shutil.copy2(Path(plan_path), output_dir / "code_module_plan.json")

    # Copy proposed patch summary
    patch_path = state.get("proposed_patch_path", "")
    if patch_path and Path(patch_path).exists():
        patch = json.loads(Path(patch_path).read_text())
        patch_summary = {
            "total_files": len(patch.get("changed_files", [])),
            "file_paths": [
                f.get("path", "?") for f in patch.get("changed_files", [])
                if isinstance(f, dict)
            ],
        }
        (output_dir / "proposed_patch_summary.json").write_text(
            json.dumps(patch_summary, indent=2, ensure_ascii=False)
        )

    # Generate no_simplification report
    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text())
        policy = model_ir.get("simplification_policy", {})
        no_simp = {
            "allow_simplification": policy.get("allow_simplification", False),
            "approved_simplifications": policy.get("approved_simplifications", []),
            "status": "NO_SIMPLIFICATION" if not policy.get("allow_simplification") else "HAS_APPROVED",
        }
        (output_dir / "no_simplification_report.json").write_text(
            json.dumps(no_simp, indent=2)
        )

    # Generate geometry interface report
    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text())
        interfaces = model_ir.get("interfaces", [])
        gi_report = {
            "total_interfaces": len(interfaces),
            "interfaces": [
                {
                    "from": i.get("parent_component", "?"),
                    "to": i.get("child_component", "?"),
                    "type": i.get("interface_type", "unknown"),
                }
                for i in interfaces
            ],
        }
        (output_dir / "geometry_interface_report.json").write_text(
            json.dumps(gi_report, indent=2)
        )

    # Generate evidence traceability report
    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text())
        evidence = model_ir.get("evidence", {})
        et_report = {
            "decision": evidence.get("evidence_decision", "unknown") if isinstance(evidence, dict) else "none",
            "geometry_evidence_count": len(evidence.get("geometry", [])) if isinstance(evidence, dict) else 0,
            "materials_evidence_count": len(evidence.get("materials", [])) if isinstance(evidence, dict) else 0,
        }
        (output_dir / "evidence_traceability_report.json").write_text(
            json.dumps(et_report, indent=2)
        )

    return {
        "review_artifact_dir": str(artifact_dir),
        "errors": errors,
    }


async def generate_artifact_manifest(state: ArtifactSubgraphState) -> dict[str, Any]:
    """Generate artifact manifest for the review directory."""
    artifact_dir = Path(state.get("review_artifact_dir", ""))
    output_dir = artifact_dir / "output"
    errors = list(state.get("errors", []))

    # List all files in artifact dir
    files: list[str] = []
    if output_dir.exists():
        for f in sorted(output_dir.iterdir()):
            if f.is_file():
                files.append(f.name)

    manifest = {
        "artifact_type": "g4_complex_model",
        "job_id": state.get("job_id", "unknown"),
        "validation_status": state.get("validation_status", "UNKNOWN"),
        "files": files,
        "total_files": len(files),
    }

    manifest_path = artifact_dir / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Generate review_report.json
    review_report = {
        "artifact_type": "g4_complex_model",
        "job_id": state.get("job_id", "unknown"),
        "validation_status": state.get("validation_status", "UNKNOWN"),
        "artifacts_collected": len(files),
        "has_model_ir": "g4_model_ir.json" in files,
        "has_gate_results": "gate_results.json" in files,
        "has_model_review": "model_review_report.md" in files,
    }
    (artifact_dir / "review_report.json").write_text(
        json.dumps(review_report, indent=2)
    )

    status = "collected" if files else "failed"
    if errors and files:
        status = "partial"

    return {
        "artifact_manifest_path": str(manifest_path),
        "artifact_status": status,
    }


async def generate_artifact_readme(state: ArtifactSubgraphState) -> dict[str, Any]:
    """Generate README.md for the artifact directory."""
    artifact_dir = Path(state.get("review_artifact_dir", ""))
    validation_status = state.get("validation_status", "UNKNOWN")
    job_id = state.get("job_id", "unknown")

    readme = f"""# G4 Complex Model — Review Artifact

## Job ID
`{job_id}`

## Validation Status
**{validation_status}**

## Contents

| File | Description |
|------|-------------|
| `review_report.json` | Artifact collection summary |
| `artifact_manifest.json` | File manifest |
| `output/gate_results.json` | All gate check results |
| `output/g4_model_ir.json` | Geant4 Model IR |
| `output/component_specs_summary.json` | Component spec summary |
| `output/model_review_report.md` | Model review report |
| `output/construction_ledger.json` | Construction audit trail |
| `output/code_module_plan.json` | Code generation plan |
| `output/no_simplification_report.json` | Simplification audit |
| `output/geometry_interface_report.json` | Geometry interface report |
| `output/evidence_traceability_report.json` | Evidence traceability |

## Architecture

This artifact was generated by RadAgent v2 subgraph architecture:
- **Context Subgraph** → RAG + Web evidence
- **Task Planning Subgraph** → Task specification
- **G4 Modeling Subgraph** → Geant4 Model IR construction
- **G4 Codegen Subgraph** → Modular C++ generation
- **Gate Subgraph** → Gate 0-11 + G4-A to G4-G validation
"""
    (artifact_dir / "README.md").write_text(readme)

    return {}
