"""G4 Modeling Gates (G4-A to G4-G) — complex model validation.

These gates check the Geant4 Model IR for completeness, consistency,
and compliance with modeling policies.

Each gate outputs: gate_id, name, status, checked_items, passed_items,
failed_items, warnings, evidence, file_paths, message.
"""

from __future__ import annotations

from typing import Any

from .base_gates import gate_name
from .schemas import GateSubgraphState


async def run_g4_modeling_gates(state: GateSubgraphState) -> dict[str, Any]:
    """Run G4-A through G4-G (complex model gates)."""
    gate_results: list[dict[str, Any]] = list(state.get("gate_results", []))
    failed: list[str] = list(state.get("failed_gates", []))
    model_ir_dict = state.get("g4_model_ir", {})

    if not model_ir_dict:
        return {"gate_results": gate_results, "failed_gates": failed}

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

    try:
        model_ir = G4ModelIR.model_validate(model_ir_dict)
    except Exception as exc:
        for gid in range(12, 19):
            gate_results.append({
                "gate_id": gid,
                "name": gate_name(gid),
                "status": "fail",
                "checked_items": [{"item": "Model IR validation", "result": "fail"}],
                "passed_items": [],
                "failed_items": [f"Model IR validation error: {exc}"],
                "warnings": [],
                "evidence": [],
                "file_paths": [],
                "message": f"Invalid model IR: {exc}",
            })
            failed.append(gate_name(gid))
        return {"gate_results": gate_results, "failed_gates": failed}

    # Import validators
    from agent_core.g4_modeling.validators import (
        EvidenceTraceabilityValidator,
        GeometryInterfaceValidator,
        ModelCompletenessValidator,
        NoSimplificationValidator,
        OverlapPolicyValidator,
    )

    component_ids = [c.component_id for c in model_ir.components]
    material_ids = [m.material_id for m in model_ir.materials]
    scoring_ids = [s.scoring_id for s in model_ir.scoring]

    # G4-A: Model Completeness
    _run_detailed_gate(
        gate_results, failed, 12, "Model Completeness",
        lambda: ModelCompletenessValidator().validate(model_ir),
        checked_items=[
            {"item": f"components count ({len(component_ids)})", "result": "check"},
            {"item": f"materials count ({len(material_ids)})", "result": "check"},
            {"item": f"scoring specs count ({len(scoring_ids)})", "result": "check"},
            {"item": "simplification_policy defined", "result": "check"},
            {"item": "evidence pack present", "result": "check"},
        ],
        evidence=[f"components: {', '.join(component_ids)}"],
    )

    # G4-B: No Unapproved Simplification
    _run_detailed_gate(
        gate_results, failed, 13, "No Unapproved Simplification",
        lambda: NoSimplificationValidator().validate(model_ir),
        checked_items=[
            {"item": "no missing complex components", "result": "check"},
            {"item": "no layer merge simplification", "result": "check"},
            {"item": "all source_evidence non-empty", "result": "check"},
            {"item": "no placeholder values", "result": "check"},
        ],
        evidence=[f"component_ids: {', '.join(component_ids)}"],
        extra_fields={
            "missing_components": [],
            "unapproved_simplifications": [],
        },
    )

    # G4-C: Geometry Interface
    iface_count = len(model_ir.interfaces)
    _run_detailed_gate(
        gate_results, failed, 14, "Geometry Interface Consistency",
        lambda: GeometryInterfaceValidator().validate(model_ir),
        checked_items=[
            {"item": "exactly one world volume", "result": "check"},
            {"item": "all mother_volume references valid", "result": "check"},
            {"item": "no orphan volumes", "result": "check"},
            {"item": "no circular containment", "result": "check"},
            {"item": "all interface references valid", "result": "check"},
            {"item": "interface-hierarchy consistency", "result": "check"},
        ],
        evidence=[
            f"components: {len(component_ids)}, interfaces: {iface_count}",
            f"component_ids: {', '.join(component_ids)}",
        ],
    )

    # G4-D: Overlap Policy
    _run_detailed_gate(
        gate_results, failed, 15, "Overlap Policy",
        lambda: OverlapPolicyValidator().validate(model_ir),
        checked_items=[
            {"item": "no overlapping daughter volumes", "result": "check"},
        ],
        evidence=[],
    )

    # G4-E: Evidence Traceability
    _run_detailed_gate(
        gate_results, failed, 16, "Evidence Traceability",
        lambda: EvidenceTraceabilityValidator().validate(model_ir),
        checked_items=[
            {"item": "all components have source_evidence", "result": "check"},
            {"item": "all materials have source_evidence", "result": "check"},
            {"item": "all sources have source_evidence", "result": "check"},
            {"item": "physics has source_evidence", "result": "check"},
        ],
        evidence=["evidence_traceability_report verified"],
    )

    # G4-F: Code Module Boundary
    code_modules = state.get("code_modules", [])
    if code_modules:
        try:
            from agent_core.g4_modeling.schemas.code_module_plan import (
                CodeGenerationPlan,
                CodeModulePlan,
            )
            from agent_core.g4_modeling.validators import CodeModuleBoundaryValidator

            plans = [
                CodeModulePlan.model_validate(m)
                for m in code_modules if isinstance(m, dict)
            ]
            gen_plan = CodeGenerationPlan(
                plan_id="gate_check",
                job_id=state.get("job_id", "unknown"),
                modules=plans,
            )
            passed, errors = CodeModuleBoundaryValidator().validate(gen_plan, model_ir)
            _append_gate_detailed(
                gate_results, failed, 17, "Code Module Boundary",
                passed, errors,
                checked_items=[
                    {"item": "each module has own header", "result": "pass" if passed else "fail"},
                    {"item": "no global mutable state", "result": "pass" if passed else "fail"},
                    {"item": "clean public API", "result": "pass" if passed else "fail"},
                ],
                evidence=[f"{len(plans)} modules checked"],
            )
        except Exception as exc:
            _append_gate_detailed(
                gate_results, failed, 17, "Code Module Boundary",
                False, [f"Error: {exc}"],
                checked_items=[{"item": "module boundary validation", "result": "fail"}],
                evidence=[],
            )
    else:
        gate_results.append({
            "gate_id": 17,
            "name": "Code Module Boundary",
            "status": "skipped",
            "checked_items": [],
            "passed_items": [],
            "failed_items": [],
            "warnings": ["No code modules generated yet"],
            "evidence": [],
            "file_paths": [],
            "message": "Skipped: no code modules to validate",
        })

    # G4-G: No Magic Number
    gate_results.append({
        "gate_id": 18,
        "name": "No Magic Number",
        "status": "skipped",
        "checked_items": [
            {"item": "C++ code magic number check", "result": "deferred"},
        ],
        "passed_items": [],
        "failed_items": [],
        "warnings": ["Magic number check deferred to code review phase"],
        "evidence": [],
        "file_paths": [],
        "message": "Deferred: magic number check runs after codegen",
    })

    # G4-H: Human Confirmation
    g4_h_status = "pass"
    g4_h_checked_items: list[dict[str, str]] = []
    g4_h_passed_items: list[str] = []
    g4_h_failed_items: list[str] = []
    g4_h_warnings: list[str] = []
    g4_h_evidence: list[str] = []
    g4_h_file_paths: list[str] = []

    # Check for unconfirmed fields at IR level
    unconfirmed_fields = model_ir.unconfirmed_fields or []
    confirmed_fields = model_ir.confirmed_fields or []

    # Check for components requiring confirmation
    components_needing_confirmation = [
        c.component_id for c in model_ir.components
        if c.requires_confirmation and not c.confirmed_by_user
    ]

    if unconfirmed_fields:
        g4_h_status = "fail"
        g4_h_failed_items.extend([f"Unconfirmed field: {f}" for f in unconfirmed_fields])
        g4_h_evidence.append(f"unconfirmed_fields: {', '.join(unconfirmed_fields)}")

    if components_needing_confirmation:
        g4_h_status = "fail"
        g4_h_failed_items.extend([
            f"Component needs confirmation: {cid}"
            for cid in components_needing_confirmation
        ])
        g4_h_evidence.append(
            f"components_pending_confirmation: {', '.join(components_needing_confirmation)}"
        )

    # Build checked items with proper line breaks
    g4_h_checked_items = [
        {
            "item": f"unconfirmed_fields count ({len(unconfirmed_fields)})",
            "result": "pass" if not unconfirmed_fields else "fail",
        },
        {"item": f"confirmed_fields count ({len(confirmed_fields)})", "result": "pass"},
        {
            "item": f"components pending confirmation ({len(components_needing_confirmation)})",
            "result": "pass" if not components_needing_confirmation else "fail",
        },
        {
            "item": "assumptions_confirmed",
            "result": "pass" if model_ir.assumptions_confirmed else "fail",
        },
    ]

    g4_h_passed_items = [
        f"confirmed_fields ({len(confirmed_fields)})",
    ] if confirmed_fields else []

    if not model_ir.assumptions_confirmed:
        g4_h_failed_items.append("Assumptions not confirmed by user")

    # Check for human confirmation directory
    job_id = state.get("job_id", "unknown")
    from agent_core.config.workspace import get_job_dir
    job_dir = get_job_dir(job_id)
    confirmation_dir = job_dir / "04_human_confirmation"
    confirmation_record_path = confirmation_dir / "confirmation_record.json"

    if confirmation_record_path.exists():
        g4_h_file_paths.append(str(confirmation_record_path))
        g4_h_evidence.append(f"confirmation_record found: {confirmation_record_path}")

    gate_results.append({
        "gate_id": 19,
        "name": gate_name(19),
        "status": g4_h_status,
        "checked_items": g4_h_checked_items,
        "passed_items": g4_h_passed_items,
        "failed_items": g4_h_failed_items,
        "warnings": g4_h_warnings,
        "evidence": g4_h_evidence,
        "file_paths": g4_h_file_paths,
        "message": (
            f"Human confirmation check: {len(confirmed_fields)} confirmed, "
            f"{len(unconfirmed_fields)} unconfirmed, "
            f"{len(components_needing_confirmation)} components pending"
        ) if g4_h_status == "pass" else (
            f"Human confirmation required: {len(unconfirmed_fields)} unconfirmed fields, "
            f"{len(components_needing_confirmation)} components pending confirmation"
        ),
    })

    if g4_h_status == "fail":
        failed.append(gate_name(19))

    return {"gate_results": gate_results, "failed_gates": failed}


def _run_detailed_gate(
    gate_results: list[dict[str, Any]],
    failed: list[str],
    gate_id: int,
    gate_display_name: str,
    validator_fn: Any,
    checked_items: list[dict[str, str]],
    evidence: list[str],
    extra_fields: dict[str, Any] | None = None,
) -> None:
    """Run a validator and append detailed results."""
    try:
        passed, errors = validator_fn()
        _append_gate_detailed(
            gate_results, failed, gate_id, gate_display_name,
            passed, errors, checked_items, evidence, extra_fields,
        )
    except Exception as exc:
        _append_gate_detailed(
            gate_results, failed, gate_id, gate_display_name,
            False, [f"Validator error: {exc}"],
            checked_items=[{"item": "validator execution", "result": "fail"}],
            evidence=[],
        )


def _append_gate_detailed(
    gate_results: list[dict[str, Any]],
    failed: list[str],
    gate_id: int,
    gate_display_name: str,
    passed: bool,
    errors: list[str],
    checked_items: list[dict[str, str]],
    evidence: list[str],
    extra_fields: dict[str, Any] | None = None,
) -> None:
    """Append a gate result with full detail structure."""
    # Update checked_items results based on pass/fail
    final_items = []
    for item in checked_items:
        check_result = item.get("result", "check")
        if check_result == "check":
            check_result = "pass" if passed else "fail"
        final_items.append({"item": item["item"], "result": check_result})

    gate_entry: dict[str, Any] = {
        "gate_id": gate_id,
        "name": gate_display_name,
        "status": "pass" if passed else "fail",
        "checked_items": final_items,
        "passed_items": [i["item"] for i in final_items if i["result"] == "pass"],
        "failed_items": errors if not passed else [],
        "warnings": [],
        "evidence": evidence,
        "file_paths": [],
        "message": "All checks passed" if passed else "; ".join(errors[:5]),
    }
    if extra_fields:
        gate_entry.update(extra_fields)
    gate_results.append(gate_entry)
    if not passed:
        failed.append(gate_name(gate_id))
