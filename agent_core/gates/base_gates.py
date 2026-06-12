"""Base gates (Gate 0-11) — context, schema, patch, build, simulation checks."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any

from agent_core.gates.output_quality import REQUIRED_G4_OUTPUTS, inspect_g4_output_quality
from agent_core.tools.geant4_workbench import resolve_self_check_events
from agent_core.validators.code_structure_validator import CodeStructureValidator
from agent_core.validators.schema_validator import SchemaValidator
from agent_core.workspace.io import get_job_dir, get_output_dir
from agent_core.workspace.paths import STAGE_CODEGEN

from .gate_runner import normalize_run_mode
from .schemas import GateSubgraphState

# Gate name mapping (shared across modules)
GATE_NAMES: dict[int, str] = {
    0: "Context Sufficiency",
    1: "Task Spec Schema",
    2: "Simulation IR Schema",
    3: "Patch Format",
    4: "File Permission",
    5: "Static Check",
    6: "Build/Parse",
    7: "Unit Test",
    8: "Data Contract",
    9: "Smoke Simulation",
    10: "Benchmark Regression",
    11: "Physics Sanity",
    12: "G4-A Model Completeness",
    13: "G4-B No Unapproved Simplification",
    14: "G4-C Geometry Interface",
    15: "G4-D Overlap Policy",
    16: "G4-E Evidence Traceability",
    17: "G4-F Code Module Boundary",
    18: "G4-G No Magic Number",
    19: "G4-H Human Confirmation",
    20: "Credibility/Plausibility Assessment",
    21: "G4 Visual Review",
}


def gate_name(gate_id: int) -> str:
    """Return human-readable gate name."""
    return GATE_NAMES.get(gate_id, f"Gate {gate_id}")


async def run_base_gates(state: GateSubgraphState) -> dict[str, Any]:
    """Run Gates 0-11 (base gates)."""
    gate_results: list[dict[str, Any]] = list(state.get("gate_results", []))
    skipped: list[dict[str, Any]] = list(state.get("skipped_gates", []))  # type: ignore[arg-type]
    failed: list[str] = list(state.get("failed_gates", []))

    job_id = state.get("job_id", "unknown")
    normalize_run_mode(state.get("run_mode", "strict"))
    context_decision = state.get("context_decision", "block_no_context")
    task_spec = state.get("task_spec", {})
    model_ir = state.get("g4_model_ir", {})
    self_check_events = resolve_self_check_events(
        g4_model_ir=model_ir if isinstance(model_ir, dict) else {},
        task_spec=task_spec if isinstance(task_spec, dict) else {},
    )
    code_dir = state.get("generated_code_dir", "")
    output_dir = get_output_dir(job_id)
    _job_dir = get_job_dir(job_id)  # noqa: F841 — reserved for gate persistence

    # Gate 0: Context Sufficiency
    g0_severity = "pass"
    g0_message = "Context sufficient"
    g0_checked = [{"item": "context_decision == allow_rag or allow_with_web", "result": "pass"}]
    if context_decision == "allow_rag":
        g0_message = "Context sufficient via RAG"
    elif context_decision == "allow_with_web_supplement":
        g0_severity = "warning"
        g0_message = "Context supplemented via web search"
    elif context_decision == "block_no_context":
        g0_severity = "block"
        g0_message = "No sufficient context"
        g0_checked = [{"item": "context_decision", "result": "fail"}]
    gate_results.append(
        {
            "gate_id": 0,
            "name": gate_name(0),
            "status": g0_severity,
            "checked_items": g0_checked,
            "passed_items": [c["item"] for c in g0_checked if c["result"] == "pass"],
            "failed_items": [] if g0_severity != "block" else ["context blocked"],
            "warnings": [] if g0_severity != "warning" else ["Web supplement used"],
            "evidence": [f"context_decision: {context_decision}"],
            "file_paths": [],
            "message": g0_message,
        }
    )

    # Gate 1: Task Spec Schema
    sv = SchemaValidator()
    ts_valid, ts_errors = sv.validate_task_spec(task_spec)
    external_valid, external_errors, external_paths, external_checks = (
        _validate_external_sources(task_spec)
    )
    gate1_valid = ts_valid and external_valid
    gate1_passed = ["schema valid"] if ts_valid else []
    if external_checks and external_valid:
        gate1_passed.append("external source artifacts valid")
    gate1_failed = []
    gate1_failed.extend(ts_errors if not ts_valid else [])
    gate1_failed.extend(external_errors if not external_valid else [])
    gate_results.append(
        {
            "gate_id": 1,
            "name": gate_name(1),
            "status": "pass" if gate1_valid else "fail",
            "checked_items": [
                {
                    "item": "task_spec schema validation",
                    "result": "pass" if ts_valid else "fail",
                },
                {"item": "required fields present", "result": "pass" if ts_valid else "fail"},
                *external_checks,
            ],
            "passed_items": gate1_passed,
            "failed_items": gate1_failed,
            "warnings": [],
            "evidence": [],
            "file_paths": external_paths,
            "message": "; ".join(gate1_failed) if gate1_failed else "Task spec schema valid",
        }
    )

    # Gate 2: Simulation IR / Model IR
    if model_ir:
        try:
            from agent_core.g4_modeling.schemas.g4_model_ir import G4ModelIR

            G4ModelIR.model_validate(model_ir)
            ir_valid, ir_errors = True, []
        except Exception as exc:
            ir_valid, ir_errors = False, [str(exc)]
    else:
        ir_valid, ir_errors = False, ["No model IR loaded"]
    gate_results.append(
        {
            "gate_id": 2,
            "name": gate_name(2),
            "status": "pass" if ir_valid else "fail",
            "checked_items": [
                {"item": "Model IR loaded", "result": "pass" if model_ir else "fail"},
                {"item": "Model IR schema valid", "result": "pass" if ir_valid else "fail"},
            ],
            "passed_items": ["Model IR valid"] if ir_valid else [],
            "failed_items": ir_errors if not ir_valid else [],
            "warnings": [],
            "evidence": [],
            "file_paths": [],
            "message": "; ".join(ir_errors) if ir_errors else "Model IR schema valid",
        }
    )

    # Gate 3: Patch Format
    applied_path = state.get("applied_patch_path", "")
    patch_exists = bool(applied_path and Path(applied_path).exists())
    gate_results.append(
        {
            "gate_id": 3,
            "name": gate_name(3),
            "status": "pass" if patch_exists else "fail",
            "checked_items": [
                {"item": "applied patch file exists", "result": "pass" if patch_exists else "fail"},
            ],
            "passed_items": ["patch applied"] if patch_exists else [],
            "failed_items": [] if patch_exists else ["No applied patch found"],
            "warnings": [],
            "evidence": [applied_path] if applied_path else [],
            "file_paths": [applied_path] if applied_path else [],
            "message": "Patch applied" if patch_exists else "No applied patch found",
        }
    )

    # Gate 4: File Permission — validate patch file zones
    from agent_core.validators.file_permission_validator import FilePermissionValidator

    fpv = FilePermissionValidator()

    # Try to read patch data from applied_patch.json or proposed_patch
    patch_data: dict[str, Any] = {}
    patch_read_errors: list[str] = []
    if applied_path and Path(applied_path).exists():
        try:
            patch_data = json.loads(Path(applied_path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            patch_read_errors.append(
                f"Could not parse applied patch JSON {applied_path}: "
                f"{exc.msg} at line {exc.lineno}, column {exc.colno}"
            )
        except OSError as exc:
            patch_read_errors.append(f"Could not read applied patch {applied_path}: {exc}")

    changed_files = patch_data.get("changed_files", [])
    if not changed_files:
        # Try loading from the proposed patch if available
        proposed_path = state.get("proposed_patch_path", "")
        if not proposed_path:
            proposed_path = str(get_job_dir(job_id) / STAGE_CODEGEN / "proposed_patch.json")
        if proposed_path and Path(str(proposed_path)).exists():
            try:
                proposed_data = json.loads(Path(str(proposed_path)).read_text(encoding="utf-8"))
                changed_files = proposed_data.get("changed_files", [])
            except json.JSONDecodeError as exc:
                patch_read_errors.append(
                    f"Could not parse proposed patch JSON {proposed_path}: "
                    f"{exc.msg} at line {exc.lineno}, column {exc.colno}"
                )
            except OSError as exc:
                patch_read_errors.append(f"Could not read proposed patch {proposed_path}: {exc}")

    if changed_files:
        perm_valid, perm_errors = fpv.validate_patch_permissions(changed_files)
        red_files = [f.get("path", "?") for f in changed_files if f.get("zone") == "red"]
        g4_status = "pass" if perm_valid else "fail"
        g4_checked = [
            {"item": "all files in green zone", "result": "pass" if perm_valid else "fail"},
        ]
        if red_files:
            g4_checked.append({"item": f"red zone files: {len(red_files)}", "result": "fail"})
    else:
        # No patch data available — cannot validate.
        perm_valid = False
        perm_errors = patch_read_errors or ["No patch data available for permission check"]
        g4_status = "fail"
        g4_checked = [{"item": "patch file zones", "result": g4_status}]

    gate_results.append(
        {
            "gate_id": 4,
            "name": gate_name(4),
            "status": g4_status,
            "checked_items": g4_checked,
            "passed_items": ["all files green zone"] if perm_valid else [],
            "failed_items": perm_errors if not perm_valid else [],
            "warnings": [],
            "evidence": [f"checked {len(changed_files)} files"] if changed_files else [],
            "file_paths": [],
            "message": "; ".join(perm_errors) if perm_errors else "All files in green zone",
        }
    )

    # Gate 5: Static Structure
    if code_dir and Path(code_dir).exists():
        csv_ = CodeStructureValidator()
        struct_valid, struct_errors = csv_.validate_geant4_project(str(code_dir))
        gate_results.append(
            {
                "gate_id": 5,
                "name": gate_name(5),
                "status": "pass" if struct_valid else "fail",
                "checked_items": [
                    {"item": "code directory exists", "result": "pass"},
                    {
                        "item": "src/*.cc files present",
                        "result": "pass" if struct_valid else "fail",
                    },
                    {
                        "item": "include/*.hh files present",
                        "result": "pass" if struct_valid else "fail",
                    },
                    {
                        "item": "CMakeLists.txt valid",
                        "result": "pass" if struct_valid else "fail",
                    },
                ],
                "passed_items": ["structure valid"] if struct_valid else [],
                "failed_items": struct_errors if not struct_valid else [],
                "warnings": [],
                "evidence": [f"code_dir: {code_dir}"],
                "file_paths": [code_dir],
                "message": "; ".join(struct_errors)
                if struct_errors
                else "Geant4 code structure valid",
            }
        )
    else:
        gate_results.append(
            {
                "gate_id": 5,
                "name": gate_name(5),
                "status": "fail",
                "checked_items": [{"item": "code directory exists", "result": "fail"}],
                "passed_items": [],
                "failed_items": ["Generated code directory not found"],
                "warnings": [],
                "evidence": [],
                "file_paths": [],
                "message": "Generated code directory not found",
            }
        )

    # Gate 6: Build/Parse
    g6_severity = "fail"
    g6_message = "Build not verified"
    build_result: dict[str, Any] = {}
    try:
        from agent_core.tools.geant4_runner import Geant4Runner

        runner = Geant4Runner()
        if runner.geant4_available:
            build_result = await runner.smoke_test(
                str(code_dir),
                job_id=job_id,
                output_dir=str(output_dir),
                events=self_check_events,
            )
            build_valid = build_result.get("success", False)
            g6_msg = (
                "Build passed"
                if build_valid
                else str(
                    build_result.get("errors", "Build failed"),
                )
            )
            g6_severity = "pass" if build_valid else "fail"
            g6_message = g6_msg
        else:
            g6_message = "Geant4 environment required for build gate"
    except Exception as e:
        g6_message = f"Build check error: {e}"
    build_artifact_paths = [
        str(path)
        for path in (
            output_dir / "cmake_configure_result.json",
            output_dir / "build_result.json",
        )
        if path.is_file()
    ]
    gate_results.append(
        {
            "gate_id": 6,
            "name": gate_name(6),
            "status": g6_severity,
            "checked_items": [
                {"item": "build/parse verification", "result": g6_severity},
            ],
            "passed_items": ["build passed"] if g6_severity == "pass" else [],
            "failed_items": [g6_message] if g6_severity == "fail" else [],
            "warnings": [],
            "evidence": build_artifact_paths,
            "file_paths": build_artifact_paths,
            "message": g6_message,
        }
    )

    # Gate 7: Unit Test — uses the real ctest artifact from Geant4Runner.
    unit_result_path = output_dir / "unit_test_result.json"
    if unit_result_path.is_file():
        unit_result = json.loads(unit_result_path.read_text(encoding="utf-8"))
        g7_severity = "pass" if unit_result.get("success") is True else "fail"
        g7_message = "Unit/ctest artifact passed" if g7_severity == "pass" else "ctest failed"
    else:
        g7_severity = "fail"
        g7_message = "Unit tests required; no unit test result artifact found"
    gate_results.append(
        {
            "gate_id": 7,
            "name": gate_name(7),
            "status": g7_severity,
            "checked_items": [
                {"item": "unit test execution", "result": g7_severity},
            ],
            "passed_items": ["ctest passed"] if g7_severity == "pass" else [],
            "failed_items": [g7_message] if g7_severity == "fail" else [],
            "warnings": [],
            "evidence": [str(unit_result_path)] if unit_result_path.is_file() else [],
            "file_paths": [str(unit_result_path)] if unit_result_path.is_file() else [],
            "message": g7_message,
        }
    )

    smoke_result_path = output_dir / "smoke_simulation_result.json"
    smoke_result: dict[str, Any] = {}
    if smoke_result_path.is_file():
        try:
            data = json.loads(smoke_result_path.read_text(encoding="utf-8"))
            smoke_result = data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            smoke_result = {}
    output_quality = inspect_g4_output_quality(
        output_dir,
        smoke_result=smoke_result,
        expected_events=self_check_events,
    )

    # Gate 8: Data Contract
    if output_dir.is_dir():
        required_files = REQUIRED_G4_OUTPUTS
        present = [f for f in required_files if (output_dir / f).is_file()]
        contract_errors = [
            error
            for error in output_quality.errors
            if not error.startswith("Smoke simulation stderr contains:")
        ]
        gate_results.append(
            {
                "gate_id": 8,
                "name": gate_name(8),
                "status": "pass" if not contract_errors else "fail",
                "checked_items": [
                    {"item": f, "result": "pass" if f in present else "fail"}
                    for f in required_files
                ],
                "passed_items": present,
                "failed_items": contract_errors,
                "warnings": output_quality.warnings,
                "evidence": [f"output_dir: {output_dir}"],
                "file_paths": [str(output_dir / f) for f in present],
                "message": "; ".join(contract_errors[:5])
                if contract_errors
                else "All output files present and populated",
            }
        )
    else:
        gate_results.append(
            {
                "gate_id": 8,
                "name": gate_name(8),
                "status": "fail",
                "checked_items": [{"item": "output directory exists", "result": "fail"}],
                "passed_items": [],
                "failed_items": ["No simulation output directory"],
                "warnings": [],
                "evidence": [],
                "file_paths": [],
                "message": "No simulation output directory",
            }
        )

    # Gate 9: Smoke Simulation — uses the real smoke artifact from Geant4Runner.
    if smoke_result_path.is_file():
        smoke_errors = [
            error
            for error in output_quality.errors
            if error.startswith("Smoke simulation stderr contains:")
        ]
        g9_severity = (
            "pass" if smoke_result.get("success") is True and not smoke_errors else "fail"
        )
        g9_message = (
            "Smoke simulation passed"
            if g9_severity == "pass"
            else "; ".join(smoke_errors) or "Smoke failed"
        )
    else:
        g9_severity = "fail"
        g9_message = "Smoke simulation required; no smoke simulation result artifact found"
    gate_results.append(
        {
            "gate_id": 9,
            "name": gate_name(9),
            "status": g9_severity,
            "checked_items": [
                {"item": f"smoke simulation ({self_check_events} events)", "result": g9_severity},
            ],
            "passed_items": ["smoke simulation passed"] if g9_severity == "pass" else [],
            "failed_items": [g9_message] if g9_severity == "fail" else [],
            "warnings": [],
            "evidence": [str(smoke_result_path)] if smoke_result_path.is_file() else [],
            "file_paths": [str(smoke_result_path)] if smoke_result_path.is_file() else [],
            "message": g9_message,
        }
    )

    # Gate 10: Benchmark Regression
    gate_results.append(
        {
            "gate_id": 10,
            "name": gate_name(10),
            "status": "skipped",
            "critical": False,
            "checked_items": [{"item": "benchmark regression check", "result": "skipped"}],
            "passed_items": [],
            "failed_items": [],
            "warnings": [],
            "evidence": [],
            "file_paths": [],
            "message": "No matching benchmark case; explicitly non-critical",
        }
    )

    # Gate 11: Physics Sanity
    physics_errors: list[str] = [
        error
        for error in output_quality.errors
        if (
            "edep_3d.csv" in error
            or "dose_3d.csv" in error
            or "event_table.csv" in error
            or "Smoke simulation stderr" in error
        )
    ]
    if output_dir.is_dir():
        for csv_name, field_names in [
            ("edep_3d.csv", ("edep_MeV", "edep")),
            ("dose_3d.csv", ("dose_Gy", "dose")),
        ]:
            csv_path = output_dir / csv_name
            if csv_path.is_file():
                try:
                    with open(csv_path, newline="", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for i, row in enumerate(reader):
                            for field in field_names:
                                val = row.get(field)
                                if val is not None:
                                    try:
                                        v = float(val)
                                        if math.isnan(v) or math.isinf(v):
                                            physics_errors.append(f"{csv_name} row {i}: NaN/Inf")
                                        elif v < 0:
                                            physics_errors.append(f"{csv_name} row {i}: negative")
                                    except (ValueError, TypeError):
                                        physics_errors.append(
                                            f"{csv_name} row {i}: non-numeric {field}"
                                        )
                                    break
                except Exception as e:
                    physics_errors.append(f"Error reading {csv_name}: {e}")
    if not output_dir.is_dir():
        physics_errors.append("No simulation output directory for physics sanity checks")
    gate_results.append(
        {
            "gate_id": 11,
            "name": gate_name(11),
            "status": "pass" if not physics_errors else "fail",
            "checked_items": [
                {
                    "item": "edep values non-negative, finite",
                    "result": "pass" if not physics_errors else "fail",
                },
                {
                    "item": "dose values non-negative, finite",
                    "result": "pass" if not physics_errors else "fail",
                },
            ],
            "passed_items": ["physics sanity passed"] if not physics_errors else [],
            "failed_items": physics_errors[:5],
            "warnings": [],
            "evidence": [],
            "file_paths": [],
            "message": "; ".join(physics_errors[:5]) if physics_errors else "Physics sanity passed",
        }
    )

    # Collect failed gate names
    for g in gate_results:
        if g.get("status") in ("fail", "block", "blocked"):
            failed.append(g.get("name", f"Gate {g.get('gate_id')}"))

    return {
        "gate_results": gate_results,
        "skipped_gates": skipped,
        "failed_gates": failed,
    }


def _validate_external_sources(
    task_spec: dict[str, Any],
) -> tuple[bool, list[str], list[str], list[dict[str, str]]]:
    """Validate declared external source artifacts after TaskSpec schema checks."""
    sources = task_spec.get("external_sources")
    if not sources:
        return True, [], [], []
    if not isinstance(sources, list):
        return False, ["external_sources must be a list"], [], []

    errors: list[str] = []
    file_paths: list[str] = []
    checked: list[dict[str, str]] = []
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or f"external_sources[{index}]")
        status = str(source.get("status") or "")
        raw_artifacts = source.get("artifact_paths") or []
        artifact_paths = raw_artifacts if isinstance(raw_artifacts, list) else []
        if status == "ready" and not artifact_paths:
            errors.append(f"ready external source {source_id} has no artifact_paths")
        for artifact in artifact_paths:
            path = Path(str(artifact))
            item = f"external source artifact {path}"
            if path.is_file():
                checked.append({"item": item, "result": "pass"})
                file_paths.append(str(path))
            else:
                checked.append({"item": item, "result": "fail"})
                errors.append(f"Missing external source artifact: {path}")
    return not errors, errors, file_paths, checked
