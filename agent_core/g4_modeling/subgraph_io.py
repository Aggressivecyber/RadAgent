"""G4 Modeling Subgraph — I/O adapters.

Bridges between the subgraph state and existing nodes:
- Loads task_spec from file before passing to nodes
- Persists g4_model_ir to disk after each node
- Extracts output paths for the main graph
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_stage_dir

from .subgraph_state import G4ModelingSubgraphState


async def load_task_spec(state: G4ModelingSubgraphState) -> dict[str, Any]:
    """Load task spec from file path into state for node consumption."""
    task_spec_path = state.get("task_spec_path", "")
    if task_spec_path and Path(task_spec_path).exists():
        task_spec = json.loads(Path(task_spec_path).read_text())
    else:
        task_spec = {}

    return {
        "task_spec": task_spec,
        "modeling_mode": "realistic",
        "retry_count": 0,
        "errors": [],
    }


async def persist_model_ir(state: G4ModelingSubgraphState) -> dict[str, Any]:
    """Persist the g4_model_ir to disk and generate all output paths."""
    job_id = state.get("job_id", "unknown")
    model_ir_dict = state.get("g4_model_ir", {})

    if not model_ir_dict:
        return {
            "g4_modeling_status": "failed",
            "errors": ["No g4_model_ir generated"],
        }

    model_ir_dir = get_stage_dir(job_id, "03_model_ir")
    model_ir_dir.mkdir(parents=True, exist_ok=True)

    # Save main IR
    ir_path = model_ir_dir / "g4_model_ir.json"
    ir_path.write_text(json.dumps(model_ir_dict, indent=2, ensure_ascii=False))

    # Save component specs
    specs_dir = model_ir_dir / "component_specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    components = model_ir_dict.get("components", [])
    for comp in components:
        comp_id = comp.get("component_id", "unknown")
        spec_path = specs_dir / f"{comp_id}.json"
        spec_path.write_text(json.dumps(comp, indent=2, ensure_ascii=False))

    # Save interfaces
    interfaces = model_ir_dict.get("interfaces", [])
    interfaces_path = model_ir_dir / "interfaces.json"
    interfaces_path.write_text(json.dumps(interfaces, indent=2, ensure_ascii=False))

    # Save material spec
    materials = model_ir_dict.get("materials", [])
    mat_path = model_ir_dir / "material_spec.json"
    mat_path.write_text(json.dumps(materials, indent=2, ensure_ascii=False))

    # Save source spec
    sources = model_ir_dict.get("sources", [])
    src_path = model_ir_dir / "source_spec.json"
    src_path.write_text(json.dumps(sources, indent=2, ensure_ascii=False))

    # Save physics spec
    physics = model_ir_dict.get("physics", {})
    phys_path = model_ir_dir / "physics_spec.json"
    phys_path.write_text(json.dumps(physics, indent=2, ensure_ascii=False))

    # Save scoring spec
    scoring = model_ir_dict.get("scoring", [])
    score_path = model_ir_dir / "scoring_spec.json"
    score_path.write_text(json.dumps(scoring, indent=2, ensure_ascii=False))

    # Save sensitive detector spec
    sds = model_ir_dict.get("sensitive_detectors", [])
    sd_path = model_ir_dir / "sensitive_detector_spec.json"
    sd_path.write_text(json.dumps(sds, indent=2, ensure_ascii=False))

    # Save construction ledger
    ledger = model_ir_dict.get("ledger", {})
    ledger_path = model_ir_dir / "construction_ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False))

    # Save model review report
    review_report = state.get("model_review_report", "")
    review_path = model_ir_dir / "model_review_report.md"
    review_path.write_text(review_report if review_report else "# Model Review\n\nNo review generated.\n")

    # Determine status
    errors = state.get("model_ir_errors", [])
    status = "passed" if not errors else "failed"

    return {
        "g4_model_ir_path": str(ir_path),
        "component_specs_dir": str(specs_dir),
        "interfaces_path": str(interfaces_path),
        "construction_ledger_path": str(ledger_path),
        "model_review_report_path": str(review_path),
        "g4_modeling_status": status,
    }
