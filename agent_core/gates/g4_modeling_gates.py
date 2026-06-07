"""G4 Modeling Gates (G4-A to G4-G) — complex model validation.

These gates check the Geant4 Model IR for completeness, consistency,
and compliance with modeling policies.
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
    except Exception:
        for gid in range(12, 19):
            gate_results.append({
                "gate_id": gid, "gate_name": gate_name(gid),
                "passed": False, "severity": "fail",
                "message": "Invalid model IR",
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

    # G4-A: Model Completeness
    _run_single_gate(
        gate_results, failed, 12,
        lambda: ModelCompletenessValidator().validate(model_ir),
    )

    # G4-B: No Unapproved Simplification
    _run_single_gate(
        gate_results, failed, 13,
        lambda: NoSimplificationValidator().validate(model_ir),
    )

    # G4-C: Geometry Interface
    _run_single_gate(
        gate_results, failed, 14,
        lambda: GeometryInterfaceValidator().validate(model_ir),
    )

    # G4-D: Overlap Policy
    _run_single_gate(
        gate_results, failed, 15,
        lambda: OverlapPolicyValidator().validate(model_ir),
    )

    # G4-E: Evidence Traceability
    _run_single_gate(
        gate_results, failed, 16,
        lambda: EvidenceTraceabilityValidator().validate(model_ir),
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
            _append_gate(gate_results, failed, 17, passed, errors)
        except Exception as exc:
            _append_gate(gate_results, failed, 17, False, [f"Error: {exc}"])
    else:
        gate_results.append({
            "gate_id": 17, "gate_name": gate_name(17),
            "passed": True, "severity": "skipped", "message": "No code modules yet",
        })

    # G4-G: No Magic Number
    gate_results.append({
        "gate_id": 18, "gate_name": gate_name(18),
        "passed": True, "severity": "skipped",
        "message": "Magic number check deferred to code review",
    })

    return {"gate_results": gate_results, "failed_gates": failed}


def _run_single_gate(
    gate_results: list[dict[str, Any]],
    failed: list[str],
    gate_id: int,
    validator_fn: Any,
) -> None:
    """Run a single validator and append results."""
    try:
        passed, errors = validator_fn()
        _append_gate(gate_results, failed, gate_id, passed, errors)
    except Exception as exc:
        _append_gate(gate_results, failed, gate_id, False, [f"Validator error: {exc}"])


def _append_gate(
    gate_results: list[dict[str, Any]],
    failed: list[str],
    gate_id: int,
    passed: bool,
    errors: list[str],
) -> None:
    """Append a gate result entry."""
    severity = "pass" if passed else "fail"
    message = "Passed" if passed else "; ".join(errors[:5])
    gate_results.append({
        "gate_id": gate_id,
        "gate_name": gate_name(gate_id),
        "passed": passed,
        "severity": severity,
        "message": message,
    })
    if not passed:
        failed.append(gate_name(gate_id))
