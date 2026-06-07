"""Artifact Subgraph nodes — collect GitHub-reviewable artifacts.

Only collects summaries, never full simulation_workspace/jobs or
large simulation output files.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
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
        allow_simp = policy.get("allow_simplification", False)
        no_simp = {
            "allow_simplification": allow_simp,
            "approved_simplifications": policy.get("approved_simplifications", []),
            "status": "HAS_APPROVED" if allow_simp else "NO_SIMPLIFICATION",
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
                    "interface_id": i.get("interface_id", "?"),
                    "component_a": i.get("component_a", "?"),
                    "component_b": i.get("component_b", "?"),
                    "relationship": i.get("relationship", "unknown"),
                    "overlap_check_enabled": i.get("overlap_check_enabled", True),
                }
                for i in interfaces
            ],
        }
        (output_dir / "geometry_interface_report.json").write_text(
            json.dumps(gi_report, indent=2, ensure_ascii=False)
        )

    # Generate evidence traceability report
    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text())
        evidence = model_ir.get("evidence", {})
        is_dict = isinstance(evidence, dict)
        et_report = {
            "decision": evidence.get("evidence_decision", "unknown") if is_dict else "none",
            "geometry_evidence_count": len(evidence.get("geometry", [])) if is_dict else 0,
            "materials_evidence_count": len(evidence.get("materials", [])) if is_dict else 0,
        }
        (output_dir / "evidence_traceability_report.json").write_text(
            json.dumps(et_report, indent=2)
        )

    return {
        "review_artifact_dir": str(artifact_dir),
        "errors": errors,
    }


async def generate_artifact_manifest(state: ArtifactSubgraphState) -> dict[str, Any]:
    """Generate rich artifact manifest with checksums and metadata."""
    artifact_dir = Path(state.get("review_artifact_dir", ""))
    output_dir = artifact_dir / "output"
    errors = list(state.get("errors", []))

    # Build rich file entries with sha256 + size
    file_entries: list[dict[str, Any]] = []
    sha256_map: dict[str, str] = {}
    size_map: dict[str, int] = {}

    if output_dir.exists():
        for f in sorted(output_dir.iterdir()):
            if f.is_file():
                content = f.read_bytes()
                sha = hashlib.sha256(content).hexdigest()
                file_entries.append({
                    "name": f.name,
                    "size_bytes": len(content),
                    "sha256": sha,
                })
                rel = f"output/{f.name}"
                sha256_map[rel] = sha
                size_map[rel] = len(content)

    # Get git commit if available
    source_commit = ""
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            source_commit = result.stdout.strip()
    except Exception:
        pass

    # Extract model IR summary
    model_ir_summary = _extract_model_ir_summary(state)

    # Collect skipped gates
    gate_results = state.get("gate_results", [])
    skipped_gates = [
        {"gate_id": g.get("gate_id"), "name": g.get("name", "")}
        for g in gate_results
        if g.get("status") == "skipped"
    ]

    # Determine run type
    execution_mode = state.get("execution_mode", "dev")
    run_type = "dev" if "dev" in execution_mode else "acceptance"

    # Determine known limitations
    known_limitations: list[str] = []
    validation_status = state.get("validation_status", "UNKNOWN")

    # CRITICAL: dev 模式禁止 VERIFIED 状态
    # 如果 run_type 是 dev 且 validation_status 是 VERIFIED，强制降级为 PARTIAL
    if run_type == "dev" and validation_status == "VERIFIED":
        validation_status = "PARTIAL"
        known_limitations.append(
            "Dev mode run — validation status downgraded from VERIFIED to PARTIAL"
        )

    if validation_status == "PARTIAL" and "Some gates skipped" not in " ".join(known_limitations):
        known_limitations.append("Some gates skipped — not all validations ran")
    if skipped_gates:
        known_limitations.append(
            f"{len(skipped_gates)} gate(s) skipped: "
            + ", ".join(str(g.get("name", g.get("gate_id"))) for g in skipped_gates)
        )

    manifest = {
        "schema_version": "v3",
        "artifact_type": "g4_complex_model",
        "job_id": state.get("job_id", "unknown"),
        "validation_status": validation_status,
        "generated_at": datetime.now(UTC).isoformat(),
        "is_stub": False,
        "run_type": run_type,
        "source_commit": source_commit,
        "source_job_id": state.get("job_id", "unknown"),
        "files": file_entries,
        "sha256": sha256_map,
        "size_bytes": size_map,
        "total_files": len(file_entries),
        "model_ir_summary": model_ir_summary,
        "skipped_gates": skipped_gates,
        "known_limitations": known_limitations,
    }

    manifest_path = artifact_dir / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    # Generate review_report.json (rich version)
    file_names = [e["name"] for e in file_entries]
    review_report = {
        "schema_version": "v3",
        "artifact_type": "g4_complex_model",
        "job_id": state.get("job_id", "unknown"),
        "validation_status": validation_status,
        "generated_at": datetime.now(UTC).isoformat(),
        "is_stub": False,
        "run_type": run_type,
        "artifacts_collected": len(file_entries),
        "has_model_ir": "g4_model_ir.json" in file_names,
        "has_gate_results": "gate_results.json" in file_names,
        "has_model_review": "model_review_report.md" in file_names,
        "has_manifest": "artifact_manifest.json" in file_names,
        "file_count": len(file_entries),
        "skipped_gates": skipped_gates,
        "known_limitations": known_limitations,
    }
    (artifact_dir / "review_report.json").write_text(
        json.dumps(review_report, indent=2, ensure_ascii=False)
    )

    status = "collected" if file_entries else "failed"
    if errors and file_entries:
        status = "partial"

    return {
        "artifact_manifest_path": str(manifest_path),
        "artifact_status": status,
    }


def _extract_model_ir_summary(state: dict[str, Any]) -> dict[str, Any]:
    """Extract lightweight model IR summary from state."""
    model_ir = state.get("g4_model_ir", {})
    if not model_ir and state.get("g4_model_ir_path"):
        ir_path = Path(state["g4_model_ir_path"])
        if ir_path.exists():
            model_ir = json.loads(ir_path.read_text())

    if not model_ir:
        return {
            "components": [],
            "materials_count": 0,
            "scoring_count": 0,
        }

    components = model_ir.get("components", [])
    return {
        "components": [
            {
                "component_id": c.get("component_id", "?"),
                "component_type": c.get("component_type", "?"),
                "geometry_type": c.get("geometry_type", "?"),
            }
            for c in components
        ],
        "materials_count": len(model_ir.get("materials", [])),
        "scoring_count": len(model_ir.get("scoring", [])),
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
