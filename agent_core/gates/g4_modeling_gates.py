"""G4 Modeling Gates (G4-A to G4-H) — complex model validation.

These gates check the Geant4 Model IR for completeness, consistency,
and compliance with modeling policies.

Each gate outputs: gate_id, name, status, checked_items, passed_items,
failed_items, warnings, evidence, file_paths, message.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base_gates import gate_name
from .schemas import GateSubgraphState


async def run_g4_modeling_gates(state: GateSubgraphState) -> dict[str, Any]:
    """Run G4-A through G4-H (complex model gates)."""
    gate_results: list[dict[str, Any]] = list(state.get("gate_results", []))
    failed: list[str] = list(state.get("failed_gates", []))
    model_ir_dict = state.get("g4_model_ir", {})

    if not model_ir_dict:
        return {"gate_results": gate_results, "failed_gates": failed}

    from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

    try:
        model_ir = G4ModelIR.model_validate(model_ir_dict)
    except Exception as exc:
        for gid in range(12, 20):
            gate_results.append(
                {
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
                }
            )
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
        gate_results,
        failed,
        12,
        "Model Completeness",
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
        gate_results,
        failed,
        13,
        "No Unapproved Simplification",
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
        gate_results,
        failed,
        14,
        "Geometry Interface Consistency",
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
        gate_results,
        failed,
        15,
        "Overlap Policy",
        lambda: OverlapPolicyValidator().validate(model_ir),
        checked_items=[
            {"item": "no overlapping daughter volumes", "result": "check"},
        ],
        evidence=[],
    )

    # G4-E: Evidence Traceability
    _run_detailed_gate(
        gate_results,
        failed,
        16,
        "Evidence Traceability",
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
    generated_modules = _load_generated_code_modules(state.get("generated_code_dir", ""))
    if code_modules:
        try:
            from agent_core.g4_modeling.schemas.code_module_plan import (
                CodeGenerationPlan,
                CodeModulePlan,
            )
            from agent_core.g4_modeling.validators import CodeModuleBoundaryValidator

            plans = [CodeModulePlan.model_validate(m) for m in code_modules if isinstance(m, dict)]
            gen_plan = CodeGenerationPlan(
                plan_id="gate_check",
                job_id=state.get("job_id", "unknown"),
                modules=plans,
            )
            passed, errors = CodeModuleBoundaryValidator().validate(gen_plan, model_ir)
            _append_gate_detailed(
                gate_results,
                failed,
                17,
                "Code Module Boundary",
                passed,
                errors,
                checked_items=[
                    {"item": "each module has own header", "result": "pass" if passed else "fail"},
                    {"item": "no global mutable state", "result": "pass" if passed else "fail"},
                    {"item": "clean public API", "result": "pass" if passed else "fail"},
                ],
                evidence=[f"{len(plans)} modules checked"],
            )
        except Exception as exc:
            _append_gate_detailed(
                gate_results,
                failed,
                17,
                "Code Module Boundary",
                False,
                [f"Error: {exc}"],
                checked_items=[{"item": "module boundary validation", "result": "fail"}],
                evidence=[],
            )
    elif generated_modules:
        passed, errors, checked_items, evidence, file_paths = _validate_generated_boundaries(
            generated_modules
        )
        _append_gate_detailed(
            gate_results,
            failed,
            17,
            "Code Module Boundary",
            passed,
            errors,
            checked_items=checked_items,
            evidence=evidence,
            extra_fields={"file_paths": file_paths},
        )
    else:
        _append_gate_detailed(
            gate_results,
            failed,
            17,
            "Code Module Boundary",
            False,
            ["No generated C++ modules available for boundary validation"],
            checked_items=[{"item": "generated C++ modules available", "result": "fail"}],
            evidence=[],
        )

    # G4-G: No Magic Number
    if generated_modules:
        from agent_core.g4_codegen.validators.no_magic_number import validate_no_magic_numbers

        passed, errors = validate_no_magic_numbers(generated_modules)
        file_paths = [
            str(m["file_path"])
            for m in generated_modules
            if isinstance(m.get("file_path"), Path)
        ]
        _append_gate_detailed(
            gate_results,
            failed,
            18,
            "No Magic Number",
            passed,
            errors,
            checked_items=[
                {
                    "item": f"C++ code magic number check ({len(generated_modules)} files)",
                    "result": "pass" if passed else "fail",
                },
            ],
            evidence=[f"{len(generated_modules)} generated files scanned"],
            extra_fields={"file_paths": file_paths},
        )
    else:
        _append_gate_detailed(
            gate_results,
            failed,
            18,
            "No Magic Number",
            False,
            ["No generated C++ modules available for magic-number validation"],
            checked_items=[{"item": "generated C++ modules available", "result": "fail"}],
            evidence=[],
        )

    # G4-H: Human Confirmation Completeness
    from agent_core.human_confirmation.validators import validate_human_confirmation_state

    hc_result = validate_human_confirmation_state(state)
    gate_results.append(
        {
            "gate_id": 19,
            "name": gate_name(19),
            "status": "pass" if hc_result["passed"] else "fail",
            "checked_items": [
                {"item": item, "result": "pass" if hc_result["passed"] else "fail"}
                for item in hc_result["checked_items"]
            ],
            "passed_items": hc_result["checked_items"] if hc_result["passed"] else [],
            "failed_items": hc_result["failed_items"],
            "warnings": [],
            "evidence": [state.get("confirmation_record_path", "")],
            "file_paths": [
                state.get("confirmation_record_path", ""),
                state.get("confirmed_model_plan_path", ""),
            ],
            "message": hc_result["message"],
        }
    )

    if not hc_result["passed"]:
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
            gate_results,
            failed,
            gate_id,
            gate_display_name,
            passed,
            errors,
            checked_items,
            evidence,
            extra_fields,
        )
    except Exception as exc:
        _append_gate_detailed(
            gate_results,
            failed,
            gate_id,
            gate_display_name,
            False,
            [f"Validator error: {exc}"],
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
        "name": gate_name(gate_id),
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


def _load_generated_code_modules(generated_code_dir: str) -> list[dict[str, Any]]:
    """Load generated C++ files from geant4_project for post-codegen gates."""
    if not generated_code_dir:
        return []
    root = Path(generated_code_dir)
    if not root.is_dir():
        return []

    modules: list[dict[str, Any]] = []
    for path in sorted([root / "main.cc", *root.glob("src/*.cc"), *root.glob("include/*.hh")]):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        stem = path.stem
        modules.append(
            {
                "module_id": rel,
                "code": path.read_text(encoding="utf-8", errors="replace"),
                "header": f"include/{stem}.hh" if path.suffix == ".cc" else rel,
                "path": rel,
                "file_path": path,
            }
        )
    return modules


def _validate_generated_boundaries(
    modules: list[dict[str, Any]],
) -> tuple[bool, list[str], list[dict[str, str]], list[str], list[str]]:
    """Run practical module-boundary checks on generated source files."""
    errors: list[str] = []
    checked_items: list[dict[str, str]] = []
    evidence: list[str] = []
    file_paths: list[str] = []

    by_path = {m.get("path", ""): m for m in modules}
    src_modules = [m for m in modules if str(m.get("path", "")).startswith("src/")]
    header_modules = [m for m in modules if str(m.get("path", "")).startswith("include/")]
    file_paths = [
        str(m["file_path"])
        for m in modules
        if isinstance(m.get("file_path"), Path)
    ]

    if not src_modules:
        errors.append("No src/*.cc files found in generated code")
    if not header_modules:
        errors.append("No include/*.hh files found in generated code")

    for module in src_modules:
        path = str(module.get("path", ""))
        code = str(module.get("code", ""))
        expected_header = f"include/{Path(path).stem}.hh"
        if expected_header in by_path:
            header_name = Path(expected_header).name
            if f'#include "{header_name}"' not in code and f'#include <{header_name}>' not in code:
                errors.append(f"{path}: does not include its own header {header_name}")
        if "static " in code:
            import re

            mutable_static = re.findall(
                r"static\s+(?!const|constexpr)[A-Za-z_:<>]+\s+\w+\s*=",
                code,
            )
            if mutable_static:
                errors.append(f"{path}: has global mutable state {mutable_static[:3]}")

    checked_items.extend(
        [
            {
                "item": "src/*.cc files present",
                "result": "pass" if src_modules else "fail",
            },
            {
                "item": "include/*.hh files present",
                "result": "pass" if header_modules else "fail",
            },
            {
                "item": "source files include matching owned headers when present",
                "result": "pass"
                if not any("does not include its own header" in e for e in errors)
                else "fail",
            },
            {
                "item": "no non-const static mutable globals",
                "result": "pass"
                if not any("global mutable state" in e for e in errors)
                else "fail",
            },
        ]
    )
    evidence.append(f"{len(src_modules)} source files and {len(header_modules)} headers checked")
    return not errors, errors, checked_items, evidence, file_paths
