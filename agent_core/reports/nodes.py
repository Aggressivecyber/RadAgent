"""Report Subgraph nodes — generate final report.

The final report MUST cover:
1. passed validation status
2. Realistic status
3. Simplification disclosure
4. RAG/Web evidence sources
5. Components generated
6. Materials generated
7. Gate results
8. Failure location (if any)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir

from .schemas import ReportSubgraphState


async def generate_final_report(state: ReportSubgraphState) -> dict[str, Any]:
    """Generate the comprehensive final report."""
    job_id = state.get("job_id", "unknown")
    user_query = state.get("user_query", "")
    execution_mode = state.get("execution_mode", "strict")
    validation_status = state.get("validation_status", "failed")
    context_decision = state.get("context_decision", "unknown")
    simulation_scope = state.get("simulation_scope", [])
    failed_gates = state.get("failed_gates", [])
    errors = state.get("errors", [])

    job_dir = get_job_dir(job_id)
    report_dir = job_dir / "10_report"
    report_dir.mkdir(parents=True, exist_ok=True)

    # Load model IR info
    ir_path = state.get("g4_model_ir_path", "")
    model_ir: dict[str, Any] = {}
    if ir_path and Path(ir_path).exists():
        model_ir = json.loads(Path(ir_path).read_text())

    # Load gate results
    gate_path = state.get("gate_results_path", "")
    gate_results: list[dict[str, Any]] = []
    if gate_path and Path(gate_path).exists():
        gate_results = json.loads(Path(gate_path).read_text())

    # Determine verified status
    verified = validation_status == "passed"

    # Determine termination reason
    if verified:
        termination = "completed_passed"
    elif context_decision == "block_no_context":
        termination = "blocked_no_context"
    elif "reserved" in str(simulation_scope):
        termination = "completed_with_reserved_scope"
    elif failed_gates:
        termination = f"failed_gates: {', '.join(failed_gates[:5])}"
    elif errors:
        termination = f"errors: {'; '.join(errors[:3])}"
    else:
        termination = "completed_unverified"

    # Check for reserved scopes (TCAD/SPICE)
    reserved_scopes = [s for s in simulation_scope if s not in ("geant4",)]
    reserved_note = ""
    if reserved_scopes:
        reserved_note = (
            f"\n\n**Note:** The following scopes were requested but are reserved "
            f"for later implementation: {', '.join(reserved_scopes)}. "
            f"Only Geant4 modeling was executed in this phase."
        )

    # Model IR summary
    components = model_ir.get("components", [])
    materials = model_ir.get("materials", [])
    sources = model_ir.get("sources", [])
    scoring = model_ir.get("scoring", [])
    simplification_policy = model_ir.get("simplification_policy", {})
    open_issues = model_ir.get("open_issues", [])

    # Build report
    report_lines = [
        "# RadAgent Final Report",
        "",
        f"## Job: `{job_id}`",
        "",
        "### Overview",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| **Status** | {'passed' if verified else validation_status} |",
        f"| **Execution Mode** | `{execution_mode}` |",
        f"| **Termination Reason** | {termination} |",
        "| **Modeling Mode** | realistic |",
        f"| **Context Source** | {context_decision} |",
    ]

    if reserved_note:
        report_lines.append(reserved_note)

    # User query
    report_lines.extend(
        [
            "",
            "### User Query",
            "",
            f"> {user_query}",
        ]
    )

    # Components
    if components:
        report_lines.extend(
            [
                "",
                f"### Components ({len(components)})",
                "",
            ]
        )
        for comp in components:
            cid = comp.get("component_id", "?")
            ctype = comp.get("component_type", "?")
            mat = comp.get("material_id", "?")
            roles = ", ".join(comp.get("roles", []))
            issues = comp.get("open_issues", [])
            issue_mark = " ⚠️" if issues else ""
            report_lines.append(
                f"- **{cid}** ({ctype}): material={mat}, roles=[{roles}]{issue_mark}"
            )

    # Materials
    if materials:
        report_lines.extend(
            [
                "",
                f"### Materials ({len(materials)})",
                "",
            ]
        )
        for mat in materials:
            mid = mat.get("material_id", mat.get("name", "?"))
            density = mat.get("density_g_cm3", "?")
            custom = mat.get("custom", False)
            report_lines.append(f"- **{mid}**: density={density} g/cm³, custom={custom}")

    # Sources
    if sources:
        report_lines.extend(
            [
                "",
                f"### Particle Sources ({len(sources)})",
                "",
            ]
        )
        for src in sources:
            ptype = src.get("particle_type", "?")
            energy = src.get("energy", {})
            report_lines.append(f"- **{ptype}**: energy={energy}")

    # Scoring
    if scoring:
        report_lines.extend(
            [
                "",
                f"### Scoring ({len(scoring)})",
                "",
            ]
        )
        for sc in scoring:
            sid = sc.get("scoring_id", "?")
            stype = sc.get("scoring_type", "?")
            report_lines.append(f"- **{sid}**: type={stype}")

    # Simplification
    report_lines.extend(
        [
            "",
            "### Simplification Policy",
            "",
            f"- Allow simplification: `{simplification_policy.get('allow_simplification', False)}`",
            f"- Requires user approval: `{simplification_policy.get('requires_user_approval', True)}`",  # noqa: E501
            f"- Approved simplifications: "
            f"{len(simplification_policy.get('approved_simplifications', []))}",
        ]
    )

    # Gate results
    if gate_results:
        report_lines.extend(
            [
                "",
                f"### Gate Results ({len(gate_results)} gates)",
                "",
                "| Gate | Name | Status | Passed | Failed | Message |",
                "|------|------|--------|--------|--------|---------|",
            ]
        )
        for g in gate_results:
            gid = g.get("gate_id", "?")
            gname = g.get("name", "?")
            gstatus = g.get("status", "?")
            gmsg = g.get("message", "")[:80]
            gpassed = len(g.get("passed_items", []))
            gfailed = len(g.get("failed_items", []))
            emoji = {
                "pass": "✅",
                "warning": "⚠️",
                "fail": "❌",
                "block": "🚫",
                "skipped": "⏭️",
            }.get(gstatus, "?")
            report_lines.append(
                f"| {gid} | {gname} | {emoji} {gstatus} | {gpassed} | {gfailed} | {gmsg} |"
            )

    # Open issues
    if open_issues:
        report_lines.extend(
            [
                "",
                f"### Open Issues ({len(open_issues)})",
                "",
            ]
        )
        for issue in open_issues:
            report_lines.append(f"- {issue}")

    # Evidence sources
    evidence = model_ir.get("evidence", {})
    if isinstance(evidence, dict):
        report_lines.extend(
            [
                "",
                "### Evidence Sources",
                "",
                f"- Decision: `{evidence.get('evidence_decision', 'unknown')}`",
                f"- Geometry evidence: {len(evidence.get('geometry', []))}",
                f"- Materials evidence: {len(evidence.get('materials', []))}",
                f"- Source evidence: {len(evidence.get('source', []))}",
                f"- Physics evidence: {len(evidence.get('physics', []))}",
                f"- Scoring evidence: {len(evidence.get('scoring', []))}",
            ]
        )

    # Errors
    if errors:
        report_lines.extend(
            [
                "",
                f"### Errors ({len(errors)})",
                "",
            ]
        )
        for err in errors:
            report_lines.append(f"- {err}")

    # Architecture note
    report_lines.extend(
        [
            "",
            "---",
            "",
            "*Generated by RadAgent v2 (subgraph architecture: "
            "Context → Task Planning → G4 Modeling → G4 Codegen → "
            "Patch → Gate → Artifact → Report)*",
        ]
    )

    report_text = "\n".join(report_lines)

    # Save
    report_path = report_dir / "final_report.md"
    report_path.write_text(report_text)

    return {
        "final_report_path": str(report_path),
        "verified": verified,
        "termination_reason": termination,
    }
