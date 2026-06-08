"""Model review report node — generates human-readable model review.

Deterministic node: produces a markdown report summarizing the
complete G4ModelIR state, validation results, and codegen plan.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_core.config.workspace import get_stage_dir
from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR
from agent_core.g4_modeling.subgraph_state import G4ModelingSubgraphState as RadiationAgentState

logger = logging.getLogger(__name__)


async def model_review_report_node(state: RadiationAgentState) -> dict[str, Any]:
    """Generate model review markdown report.

    Reads: g4_model_ir, model_ir_errors, code_modules
    Writes: model_review_report, persists model_review.md
    """
    model_ir_dict = state.get("g4_model_ir", {})
    raw_errors = state.get("model_ir_errors", [])
    model_ir_errors: list[Any] = raw_errors if isinstance(raw_errors, list) else []
    raw_modules = state.get("code_modules", [])
    code_modules: list[dict[str, Any]] = raw_modules if isinstance(raw_modules, list) else []
    job_id = state.get("job_id", "")

    model_ir = G4ModelIR.model_validate(model_ir_dict)

    # Build report sections
    sections: list[str] = []

    # Header
    sections.append(f"# G4 Model Review: {model_ir.model_ir_id}")
    sections.append(f"- **Job ID**: {model_ir.job_id}")
    sections.append(f"- **Mode**: {model_ir.modeling_mode}")
    sections.append(f"- **Target**: {model_ir.target_system or 'N/A'}")
    sections.append("")

    # Validation status
    if model_ir_errors:
        sections.append("## ⚠️ Validation Issues")
        for err in model_ir_errors:
            sections.append(f"- {err}")
    else:
        sections.append("## ✅ Validation Status: PASSED")
    sections.append("")

    # Components
    sections.append("## Geometry Components")
    sections.append("| ID | Type | Material | Parent | Sensitive |")
    sections.append("|----|------|----------|--------|-----------|")
    for comp in model_ir.components:
        sensitive = "✓" if comp.sensitive else ""
        parent = comp.mother_volume or "—"
        sections.append(
            f"| {comp.component_id} | {comp.geometry_type} | "
            f"{comp.material_id} | {parent} | {sensitive} |"
        )
    sections.append("")

    # Materials
    if model_ir.materials:
        sections.append("## Materials")
        sections.append("| ID | Name | Type | Density (g/cm³) |")
        sections.append("|----|------|------|-----------------|")
        for mat in model_ir.materials:
            sections.append(
                f"| {mat.material_id} | {mat.name} | {mat.classification} | {mat.density_g_cm3} |"
            )
        sections.append("")

    # Sources
    if model_ir.sources:
        sections.append("## Particle Source")
        for src in model_ir.sources:
            sections.append(f"- **Particle**: {src.particle_type}")
            sections.append(
                f"- **Energy**: {src.energy.value} {src.energy.unit} ({src.energy.distribution})"
            )
            sections.append(f"- **Events**: {src.events}")
            sections.append(f"- **Position**: {src.beam.position} → direction {src.beam.direction}")
        sections.append("")

    # Physics
    if model_ir.physics:
        sections.append("## Physics")
        sections.append(f"- **List**: {model_ir.physics.physics_list}")
        sections.append(f"- **Reasoning**: {model_ir.physics.selection_reasoning}")
        sections.append("")

    # Sensitive detectors
    if model_ir.sensitive_detectors:
        sections.append("## Sensitive Detectors")
        for sd in model_ir.sensitive_detectors:
            sections.append(
                f"- **{sd.name}**: linked to {sd.linked_component_ids}, "
                f"collection={sd.collection_name}"
            )
        sections.append("")

    # Scoring
    if model_ir.scoring:
        sections.append("## Scoring")
        for s in model_ir.scoring:
            sections.append(f"- **{s.scoring_id}** ({s.scoring_type}): {', '.join(s.quantities)}")
        sections.append("")

    # Code modules
    if code_modules:
        sections.append("## Code Generation Plan")
        sections.append(f"Total modules: {len(code_modules)}")
        for mod in code_modules:
            sections.append(
                f"- **{mod.get('module_name', '?')}** "
                f"({mod.get('module_type', '?')}): "
                f"{len(mod.get('source_files', []))} src, "
                f"{len(mod.get('header_files', []))} hdr"
            )
        sections.append("")

    # Construction ledger
    if model_ir.ledger.steps:
        sections.append("## Construction Audit Trail")
        sections.append(f"Total steps: {len(model_ir.ledger.steps)}")
        for step in model_ir.ledger.steps[-10:]:
            sections.append(
                f"- [{step.node_name}] {step.action} → {step.target_id}: {step.description}"
            )
        if len(model_ir.ledger.steps) > 10:
            sections.append(f"- ... and {len(model_ir.ledger.steps) - 10} more entries")
        sections.append("")

    # Open issues
    if model_ir.open_issues:
        sections.append("## Open Issues")
        for issue in model_ir.open_issues:
            sections.append(f"- ⚠️ {issue}")
        sections.append("")

    report = "\n".join(sections)

    # Persist
    if job_id:
        model_ir_dir = get_stage_dir(job_id, "03_model_ir")
        model_ir_dir.mkdir(parents=True, exist_ok=True)
        report_file = model_ir_dir / "model_review.md"
        report_file.write_text(report)

    model_ir.ledger.add_entry(
        node_name="model_review_report_node",
        action="create",
        target_id="model_review",
        description=f"Generated model review report "
        f"({len(sections)} sections, {len(report)} chars)",
        modified_fields=[],
    )

    return {
        "g4_model_ir": model_ir.model_dump(mode="json"),
        "model_review_report": report,
        "current_node": "model_review_report_node",
    }
