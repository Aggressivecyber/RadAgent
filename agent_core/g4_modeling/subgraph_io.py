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

from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_MODEL_IR

from .subgraph_state import G4ModelingSubgraphState


async def load_task_spec(state: G4ModelingSubgraphState) -> dict[str, Any]:
    """Load task spec from file path into state for node consumption."""
    task_spec_path = state.get("task_spec_path", "")
    if task_spec_path and Path(task_spec_path).exists():
        task_spec = json.loads(Path(task_spec_path).read_text())
    else:
        task_spec = {}
    confirmed_plan_path = state.get("confirmed_requirement_plan_path", "")
    confirmed_plan = {}
    if confirmed_plan_path and Path(confirmed_plan_path).exists():
        confirmed_plan = json.loads(Path(confirmed_plan_path).read_text())
    if confirmed_plan:
        task_spec = dict(task_spec)
        metadata = dict(task_spec.get("metadata", {}))
        metadata["confirmed_requirement_plan_path"] = confirmed_plan_path
        task_spec["metadata"] = metadata
        task_spec["confirmed_requirement_plan"] = confirmed_plan

    return {
        "task_spec": task_spec,
        "confirmed_requirement_plan": confirmed_plan,
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

    model_ir_dir = get_stage_dir(job_id, STAGE_MODEL_IR)
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
    default_review = "# Model Review\n\nNo review generated.\n"
    review_path.write_text(review_report if review_report else default_review)

    human_confirmation_required = _requires_human_confirmation(model_ir_dict)

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
        "human_confirmation_required": human_confirmation_required,
    }


def _requires_human_confirmation(model_ir: dict[str, Any]) -> bool:
    """Return whether the persisted IR has unresolved user-confirmation items."""
    if model_ir.get("unconfirmed_fields"):
        return True
    if model_ir.get("open_issues"):
        return True

    sections = (
        "components",
        "materials",
        "sources",
        "scoring",
        "sensitive_detectors",
    )
    for section in sections:
        items = model_ir.get(section, [])
        if not isinstance(items, list):
            continue
        if any(_item_needs_confirmation(item) for item in items):
            return True

    physics = model_ir.get("physics")
    return isinstance(physics, dict) and _item_needs_confirmation(physics)


def _item_needs_confirmation(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("open_issues"):
        return True
    return bool(item.get("requires_confirmation")) and not bool(item.get("confirmed_by_user"))
