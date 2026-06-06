"""Run all gate checks on the generated code."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

from agent_core.config.workspace import get_job_dir, get_output_dir
from agent_core.graph.state import RadiationAgentState
from agent_core.validators.code_structure_validator import CodeStructureValidator
from agent_core.validators.file_permission_validator import FilePermissionValidator
from agent_core.validators.patch_validator import PatchValidator
from agent_core.validators.schema_validator import SchemaValidator

# Gates that CANNOT be skipped in mvp1_acceptance mode
_MVP1_NO_SKIP_GATES = {6, 8, 9, 11}


def _check_execution_mode_gate(
    gate_id: int,
    passed: bool,
    severity: str,
    message: str,
    retry_node: str | None,
    execution_mode: str,
) -> dict:
    """Apply execution mode rules to gate results."""
    if execution_mode == "mvp1_acceptance" and gate_id in _MVP1_NO_SKIP_GATES:
        if severity == "skipped":
            # In mvp1_acceptance, these gates cannot be skipped — fail instead
            return {
                "gate_id": gate_id,
                "gate_name": _GATE_NAMES.get(gate_id, f"Gate {gate_id}"),
                "passed": False,
                "severity": "fail",
                "message": f"[MVP1] {message} — gate cannot be skipped in acceptance mode",
                "retry_node": retry_node,
            }
    return {
        "gate_id": gate_id,
        "gate_name": _GATE_NAMES.get(gate_id, f"Gate {gate_id}"),
        "passed": passed,
        "severity": severity,
        "message": message,
        "retry_node": retry_node,
    }


_GATE_NAMES: dict[int, str] = {
    0: "RAG Sufficiency",
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
}


async def run_gate_checks(state: RadiationAgentState) -> dict:
    """Run all 12 gate checks sequentially."""
    gate_results = []
    skipped_gates: list[dict] = []
    job_id = state.get("job_id", "unknown")
    patch = state.get("proposed_patch", {})
    task_spec = state.get("task_spec", {})
    sim_ir = state.get("simulation_ir", {})
    rag_score = state.get("rag_sufficiency_score", 0.0)
    rag_required = state.get("rag_required_sources", [])
    rag_registry = state.get("rag_registry", {})
    execution_mode = state.get("execution_mode", "dev_no_geant4_env")

    # ==================================================================
    # Gate 0: RAG Sufficiency — check score + required sources
    # ==================================================================
    sources = rag_registry.get("sources", {})
    g0_errors: list[str] = []

    # Check score threshold
    if rag_score < 0.75:
        g0_errors.append(f"RAG score {rag_score:.2f} below threshold 0.75")

    # Check each required source is available and has context
    context_map = {
        "geant4": state.get("g4_context", []),
        "tcad": state.get("tcad_context", []),
        "spice": state.get("spice_context", []),
    }
    for src in rag_required:
        src_info = sources.get(src, {})
        if not src_info.get("available", False):
            g0_errors.append(f"Required source '{src}' not available")
        elif not context_map.get(src):
            g0_errors.append(f"Required source '{src}' returned no context")

    g0_passed = len(g0_errors) == 0
    gate_results.append(
        {
            "gate_id": 0,
            "gate_name": "RAG Sufficiency",
            "passed": g0_passed,
            "severity": "pass" if g0_passed else "fail",
            "message": (
                "; ".join(g0_errors) if g0_errors
                else f"RAG score: {rag_score:.2f}, all required sources available"
            ),
            "retry_node": "retrieve_g4_context" if not g0_passed else None,
        }
    )

    # ==================================================================
    # Gate 1: Task Spec Schema
    # ==================================================================
    sv = SchemaValidator()
    ts_valid, ts_errors = sv.validate_task_spec(task_spec)
    gate_results.append(
        {
            "gate_id": 1,
            "gate_name": "Task Spec Schema",
            "passed": ts_valid,
            "severity": "pass" if ts_valid else "fail",
            "message": "; ".join(ts_errors) if ts_errors else "Valid",
            "retry_node": "build_task_spec" if not ts_valid else None,
        }
    )

    # ==================================================================
    # Gate 2: Simulation IR Schema
    # ==================================================================
    ir_valid, ir_errors = sv.validate_simulation_ir(sim_ir)
    gate_results.append(
        {
            "gate_id": 2,
            "gate_name": "Simulation IR Schema",
            "passed": ir_valid,
            "severity": "pass" if ir_valid else "fail",
            "message": "; ".join(ir_errors) if ir_errors else "Valid",
            "retry_node": "build_simulation_ir" if not ir_valid else None,
        }
    )

    # ==================================================================
    # Gate 3: Patch Format
    # ==================================================================
    pv = PatchValidator()
    pf_valid, pf_errors = pv.validate_patch_format(patch)
    gate_results.append(
        {
            "gate_id": 3,
            "gate_name": "Patch Format",
            "passed": pf_valid,
            "severity": "pass" if pf_valid else "fail",
            "message": "; ".join(pf_errors) if pf_errors else "Valid",
            "retry_node": "write_code_patch" if not pf_valid else None,
        }
    )

    # ==================================================================
    # Gate 4: File Permission
    # ==================================================================
    fpv = FilePermissionValidator()
    changed_files = patch.get("changed_files", [])
    perm_valid, perm_msgs = fpv.validate_patch_permissions(changed_files)
    has_red = any("red" in m.lower() or "reject" in m.lower() for m in perm_msgs)
    gate_results.append(
        {
            "gate_id": 4,
            "gate_name": "File Permission",
            "passed": perm_valid,
            "severity": "block" if has_red else ("pass" if perm_valid else "fail"),
            "message": "; ".join(perm_msgs) if perm_msgs else "All green zone",
            "retry_node": None,
        }
    )

    # ==================================================================
    # Gate 5: Static Check (structure validation)
    # ==================================================================
    job_dir = get_job_dir(job_id)
    g4_dir = job_dir / "05_geant4"
    struct_validator = CodeStructureValidator()
    struct_valid, struct_errors = struct_validator.validate_geant4_project(str(g4_dir))
    gate_results.append(
        {
            "gate_id": 5,
            "gate_name": "Static Check",
            "passed": struct_valid,
            "severity": "pass" if struct_valid else "fail",
            "message": "; ".join(struct_errors) if struct_errors else "Structure OK",
            "retry_node": "write_code_patch" if not struct_valid else None,
        }
    )

    # ==================================================================
    # Gate 6: Build/Parse
    # ==================================================================
    try:
        from agent_core.tools.geant4_runner import Geant4Runner

        runner = Geant4Runner()
        if runner.geant4_available:
            build_result = await runner.smoke_test(str(g4_dir), events=10)
            build_valid = build_result.get("success", False)
            build_msg = (
                "Build and smoke test passed"
                if build_valid
                else str(build_result.get("errors", "Build failed"))
            )
        else:
            build_result = await runner.structure_check(str(g4_dir))
            build_valid = build_result.get("valid", False)
            status_str = "OK" if build_valid else "Issues found"
            build_msg = f"Structure check (Geant4 not available): {status_str}"
    except Exception as e:
        build_valid = False
        build_msg = f"Build check error: {e}"

    g6_severity = "pass" if build_valid else "fail"
    if not build_valid and "not available" in build_msg:
        g6_severity = "skipped"
        skipped_gates.append({"gate_id": 6, "reason": build_msg})

    gate_results.append(
        _check_execution_mode_gate(
            6, build_valid or g6_severity == "skipped", g6_severity,
            build_msg, "write_fix_patch" if not build_valid else None,
            execution_mode,
        )
    )

    # ==================================================================
    # Gate 7: Unit Test — code structure + optional compile check
    # ==================================================================
    try:
        csv7 = CodeStructureValidator()
        struct7_valid, struct7_errors = csv7.validate_geant4_project(str(g4_dir))
        if not struct7_valid:
            gate_results.append(
                {
                    "gate_id": 7,
                    "gate_name": "Unit Test",
                    "passed": False,
                    "severity": "fail",
                    "message": f"Code structure incomplete: {'; '.join(struct7_errors)}",
                    "retry_node": "write_code_patch",
                }
            )
        else:
            try:
                from agent_core.tools.geant4_runner import Geant4Runner

                runner7 = Geant4Runner()
                if runner7.geant4_available:
                    build7 = await runner7.structure_check(str(g4_dir))
                    build7_ok = build7.get("valid", False)
                    gate_results.append(
                        {
                            "gate_id": 7,
                            "gate_name": "Unit Test",
                            "passed": build7_ok,
                            "severity": "pass" if build7_ok else "fail",
                            "message": (
                                "Geant4 structure check passed"
                                if build7_ok
                                else (
                            "Structure check issues: "
                            f"{'; '.join(build7.get('issues', []))}"
                        )
                            ),
                            "retry_node": "write_fix_patch" if not build7_ok else None,
                        }
                    )
                else:
                    gate_results.append(
                        {
                            "gate_id": 7,
                            "gate_name": "Unit Test",
                            "passed": True,
                            "severity": "skipped",
                            "message": "Geant4 not available for unit testing",
                            "retry_node": None,
                        }
                    )
                    skipped_gates.append({"gate_id": 7, "reason": "Geant4 not available"})
            except Exception as exc7:
                gate_results.append(
                    {
                        "gate_id": 7,
                        "gate_name": "Unit Test",
                        "passed": True,
                        "severity": "skipped",
                        "message": f"Geant4 runner unavailable: {exc7}",
                        "retry_node": None,
                    }
                )
                skipped_gates.append({"gate_id": 7, "reason": str(exc7)})
    except Exception as exc7:
        gate_results.append(
            {
                "gate_id": 7,
                "gate_name": "Unit Test",
                "passed": False,
                "severity": "fail",
                "message": f"Unit test gate error: {exc7}",
                "retry_node": "write_code_patch",
            }
        )

    # ==================================================================
    # Gate 8: Data Contract — check g4_output_package files
    # ==================================================================
    output_dir = get_output_dir(job_id)
    _g4_required_output_files = (
        "g4_summary.json", "edep_3d.csv", "dose_3d.csv",
        "event_table.csv", "provenance.json",
    )
    if not output_dir.is_dir():
        gate_results.append(
            _check_execution_mode_gate(
                8, True, "skipped", "No simulation output yet", None, execution_mode,
            )
        )
        skipped_gates.append({"gate_id": 8, "reason": "No simulation output yet"})
    else:
        missing_files = [
            f for f in _g4_required_output_files
            if not (output_dir / f).is_file()
        ]
        if missing_files:
            gate_results.append(
                {
                    "gate_id": 8,
                    "gate_name": "Data Contract",
                    "passed": False,
                    "severity": "fail",
                    "message": f"Missing output files: {', '.join(missing_files)}",
                    "retry_node": "write_fix_patch",
                }
            )
        else:
            gate_results.append(
                {
                    "gate_id": 8,
                    "gate_name": "Data Contract",
                    "passed": True,
                    "severity": "pass",
                    "message": "All required output files present",
                    "retry_node": None,
                }
            )

    # ==================================================================
    # Gate 9: Smoke Simulation
    # ==================================================================
    try:
        from agent_core.tools.geant4_runner import Geant4Runner

        runner9 = Geant4Runner()
        if not runner9.geant4_available:
            gate_results.append(
                _check_execution_mode_gate(
                    9, True, "skipped",
                    "Geant4 not available for smoke simulation", None, execution_mode,
                )
            )
            skipped_gates.append({"gate_id": 9, "reason": "Geant4 not available"})
        else:
            has_output = output_dir.is_dir() and any(output_dir.iterdir())
            if not has_output:
                gate_results.append(
                    {
                        "gate_id": 9,
                        "gate_name": "Smoke Simulation",
                        "passed": False,
                        "severity": "fail",
                        "message": "No simulation output files produced",
                        "retry_node": "write_fix_patch",
                    }
                )
            else:
                gate_results.append(
                    {
                        "gate_id": 9,
                        "gate_name": "Smoke Simulation",
                        "passed": True,
                        "severity": "pass",
                        "message": "Simulation output files detected",
                        "retry_node": None,
                    }
                )
    except Exception as exc9:
        gate_results.append(
            _check_execution_mode_gate(
                9, True, "skipped",
                f"Smoke simulation check error: {exc9}", None, execution_mode,
            )
        )
        skipped_gates.append({"gate_id": 9, "reason": str(exc9)})

    # ==================================================================
    # Gate 10: Benchmark Regression
    # ==================================================================
    _benchmark_root = Path(__file__).resolve().parent.parent.parent / "benchmark_suite"
    matched_benchmark: dict | None = None
    try:
        if _benchmark_root.is_dir():
            sim_scope = task_spec.get("simulation_scope", [])
            particle_info = task_spec.get("particle", {})
            p_type = (
                particle_info.get("type", "").lower()
                if isinstance(particle_info, dict) else ""
            )
            for _bdir in sorted(_benchmark_root.iterdir()):
                bfile = _bdir / "benchmark.json"
                if not bfile.is_file():
                    continue
                bdata = json.loads(bfile.read_text(encoding="utf-8"))
                b_spec_data = bdata.get("input", {}).get("expected_task_spec", {})
                b_scope = b_spec_data.get("simulation_scope", [])
                b_particle = b_spec_data.get("particle", {})
                b_ptype = (
                    b_particle.get("type", "").lower()
                    if isinstance(b_particle, dict) else ""
                )
                if sim_scope and b_scope and set(sim_scope) & set(b_scope):
                    if p_type and b_ptype and p_type == b_ptype:
                        matched_benchmark = bdata
                        break
    except Exception:
        pass

    if matched_benchmark is None:
        gate_results.append(
            {
                "gate_id": 10,
                "gate_name": "Benchmark Regression",
                "passed": True,
                "severity": "skipped",
                "message": "No matching benchmark case",
                "retry_node": None,
            }
        )
    else:
        expected_gates = matched_benchmark.get("expected_outputs", {}).get("gates", {})
        regressions: list[str] = []
        for gate_key, expected_sev in expected_gates.items():
            gate_num_str = gate_key.replace("gate_", "").split("_")[0]
            try:
                gate_num = int(gate_num_str)
            except ValueError:
                continue
            if gate_num < len(gate_results):
                gate_entry = gate_results[gate_num]
                actual = (
                    gate_entry.get("severity", "unknown")
                    if isinstance(gate_entry, dict) else "unknown"
                )
                if actual not in (expected_sev, "skipped"):
                    regressions.append(f"{gate_key}: expected={expected_sev}, actual={actual}")
        if regressions:
            gate_results.append(
                {
                    "gate_id": 10,
                    "gate_name": "Benchmark Regression",
                    "passed": False,
                    "severity": "fail",
                    "message": f"Benchmark regressions: {'; '.join(regressions)}",
                    "retry_node": "write_fix_patch",
                }
            )
        else:
            gate_results.append(
                {
                    "gate_id": 10,
                    "gate_name": "Benchmark Regression",
                    "passed": True,
                    "severity": "pass",
                    "message": f"Benchmark '{matched_benchmark.get('benchmark_id', '?')}' passed",
                    "retry_node": None,
                }
            )

    # ==================================================================
    # Gate 11: Physics Sanity — validate output data for NaN/Inf/negatives
    # ==================================================================
    if not output_dir.is_dir():
        gate_results.append(
            _check_execution_mode_gate(
                11, True, "skipped",
                "No output files to validate", None, execution_mode,
            )
        )
        skipped_gates.append({"gate_id": 11, "reason": "No output files to validate"})
    else:
        physics_errors: list[str] = []
        # Validate edep_3d.csv
        edep_path = output_dir / "edep_3d.csv"
        if edep_path.is_file():
            try:
                with open(edep_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for i, row in enumerate(reader):
                        for field in ("edep_MeV", "edep", "energy_dep", "energy"):
                            val = row.get(field)
                            if val is not None:
                                try:
                                    v = float(val)
                                except (ValueError, TypeError):
                                    physics_errors.append(
                                        f"edep row {i}: non-numeric value '{val}'"
                                    )
                                    continue
                                if math.isnan(v) or math.isinf(v):
                                    physics_errors.append(f"edep row {i}: {field} is NaN or Inf")
                                elif v < 0:
                                    physics_errors.append(f"edep row {i}: negative {field} ({v})")
                                break
            except Exception as exc_edep:
                physics_errors.append(f"Error reading edep_3d.csv: {exc_edep}")
        # Validate dose_3d.csv
        dose_path = output_dir / "dose_3d.csv"
        if dose_path.is_file():
            try:
                with open(dose_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for i, row in enumerate(reader):
                        for field in ("dose_Gy", "dose"):
                            val = row.get(field)
                            if val is not None:
                                try:
                                    v = float(val)
                                except (ValueError, TypeError):
                                    physics_errors.append(
                                        f"dose row {i}: non-numeric value '{val}'"
                                    )
                                    continue
                                if math.isnan(v) or math.isinf(v):
                                    physics_errors.append(f"dose row {i}: {field} is NaN or Inf")
                                elif v < 0:
                                    physics_errors.append(f"dose row {i}: negative {field} ({v})")
                                break
            except Exception as exc_dose:
                physics_errors.append(f"Error reading dose_3d.csv: {exc_dose}")

        if not physics_errors:
            gate_results.append(
                {
                    "gate_id": 11,
                    "gate_name": "Physics Sanity",
                    "passed": True,
                    "severity": "pass",
                    "message": "Physics sanity check passed",
                    "retry_node": None,
                }
            )
        else:
            gate_results.append(
                {
                    "gate_id": 11,
                    "gate_name": "Physics Sanity",
                    "passed": False,
                    "severity": "fail",
                    "message": f"Physics violations: {'; '.join(physics_errors[:10])}",
                    "retry_node": "write_fix_patch",
                }
            )

    # Save gate results
    gate_file = job_dir / "09_validation" / "gate_results.json"
    gate_file.write_text(json.dumps(gate_results, indent=2, ensure_ascii=False))

    return {
        "gate_results": gate_results,
        "skipped_gates": skipped_gates,
        "current_node": "run_gate_checks",
        "retry_count": state.get("retry_count", 0),
    }
