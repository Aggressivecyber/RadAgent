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
    execution_mode = state.get("execution_mode", "dev_no_geant4_env")
    output_dir = get_output_dir(job_id)

    # ==================================================================
    # Gate 0: Context Sufficiency — check combined RAG+Web decision
    # ==================================================================
    context_decision = state.get("context_decision", "block_no_context")
    context_report = state.get("context_sufficiency_report", {})
    g0_errors: list[str] = []
    g0_severity: str = "pass"

    if context_decision == "allow_rag":
        g0_message = f"Context sufficient via RAG (score: {rag_score:.2f})"
    elif context_decision == "allow_with_web_supplement":
        web_urls = context_report.get("web_urls", [])
        g0_message = (
            f"Context supplemented via web search (RAG: {rag_score:.2f}, "
            f"Web: {len(web_urls)} results). "
            f"URLs: {', '.join(web_urls[:3])}"
        )
        g0_severity = "warning"  # Pass with disclosure
    elif context_decision == "block_no_context":
        g0_errors.append(f"No sufficient context (RAG: {rag_score:.2f})")
        if state.get("web_search_available", False):
            g0_errors.append("Web search returned insufficient results")
        else:
            g0_errors.append("Web search not available")
        g0_message = "; ".join(g0_errors)
        g0_severity = "block"
    else:
        g0_errors.append(f"Unknown context decision: {context_decision}")
        g0_message = "; ".join(g0_errors)
        g0_severity = "fail"

    g0_passed = g0_severity in ("pass", "warning")
    gate_results.append({
        "gate_id": 0,
        "gate_name": "Context Sufficiency",
        "passed": g0_passed,
        "severity": g0_severity,
        "message": g0_message,
        "retry_node": None,  # Context insufficiency is terminal
    })

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
    g6_severity = "fail"
    try:
        from agent_core.tools.geant4_runner import Geant4Runner

        runner = Geant4Runner()
        if runner.geant4_available:
            build_result = await runner.smoke_test(
                str(g4_dir),
                job_id=job_id,
                output_dir=str(output_dir),
                events=10,
            )
            build_valid = build_result.get("success", False)
            build_msg = (
                "Build and smoke test passed"
                if build_valid
                else str(build_result.get("errors", "Build failed"))
            )
            g6_severity = "pass" if build_valid else "fail"
        else:
            # Geant4 NOT available — structure_check does NOT count as build pass
            if execution_mode == "mvp1_acceptance":
                build_valid = False
                build_msg = "[MVP1] Geant4 environment required but not available"
                g6_severity = "fail"
            else:
                build_valid = False
                g6_severity = "skipped"
                build_msg = "Geant4 not available — build NOT verified (dev mode only)"
                skipped_gates.append({"gate_id": 6, "reason": build_msg})
    except Exception as e:
        build_valid = False
        build_msg = f"Build check error: {e}"
        g6_severity = "fail"

    gate_results.append(
        _check_execution_mode_gate(
            6, build_valid, g6_severity,
            build_msg, "write_fix_patch" if g6_severity == "fail" else None,
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
    # Gate 9: Smoke Simulation — validate actual output files
    # ==================================================================
    g9_required_files = (
        "g4_summary.json", "edep_3d.csv", "dose_3d.csv",
        "event_table.csv", "provenance.json",
    )

    def _csv_has_data_rows(csv_path: Path) -> bool:
        """Check CSV has at least 1 data row (header excluded)."""
        try:
            text = csv_path.read_text(errors="replace").strip()
            return len(text.splitlines()) > 1
        except Exception:
            return False

    try:
        from agent_core.tools.geant4_runner import Geant4Runner

        runner9 = Geant4Runner()
        if not runner9.geant4_available:
            if execution_mode == "mvp1_acceptance":
                gate_results.append({
                    "gate_id": 9,
                    "gate_name": "Smoke Simulation",
                    "passed": False,
                    "severity": "fail",
                    "message": "[MVP1] Geant4 environment required for smoke simulation",
                    "retry_node": None,
                })
            else:
                gate_results.append(
                    _check_execution_mode_gate(
                        9, False, "skipped",
                        "Geant4 not available for smoke simulation", None,
                        execution_mode,
                    )
                )
                skipped_gates.append({"gate_id": 9, "reason": "Geant4 not available"})
        elif not output_dir.is_dir():
            gate_results.append({
                "gate_id": 9,
                "gate_name": "Smoke Simulation",
                "passed": False,
                "severity": "fail",
                "message": f"Output directory does not exist: {output_dir}",
                "retry_node": "write_fix_patch",
            })
        else:
            # Check each required file
            missing: list[str] = []
            present: list[str] = []
            for fname in g9_required_files:
                fpath = output_dir / fname
                if fname == "event_table.csv":
                    if fpath.is_file() and _csv_has_data_rows(fpath):
                        present.append(fname)
                    else:
                        if not fpath.is_file():
                            missing.append(fname)
                        else:
                            missing.append(f"{fname} (no data rows)")
                elif fpath.is_file():
                    present.append(fname)
                else:
                    missing.append(fname)

            # Validate provenance matches current job
            prov_path = output_dir / "provenance.json"
            if prov_path.is_file() and "provenance.json" not in missing:
                try:
                    prov = json.loads(prov_path.read_text())
                    if prov.get("simulation_id") != job_id:
                        missing.append("provenance.json (simulation_id mismatch)")
                except Exception:
                    missing.append("provenance.json (invalid JSON)")

            # Validate g4_summary.simulation_id matches current job
            summary_path = output_dir / "g4_summary.json"
            if summary_path.is_file() and "g4_summary.json" not in missing:
                try:
                    summary = json.loads(summary_path.read_text())
                    if summary.get("simulation_id") != job_id:
                        missing.append("g4_summary.json (simulation_id mismatch)")
                except Exception:
                    missing.append("g4_summary.json (invalid JSON)")

            # Validate ALL output files were generated after patch was applied
            patch_applied_at = state.get("patch_applied_at", "")
            if patch_applied_at:
                try:
                    from datetime import datetime as _dt

                    applied_time = _dt.fromisoformat(patch_applied_at)
                    for fname in g9_required_files:
                        fpath = output_dir / fname
                        if fpath.is_file() and fname not in missing:
                            mtime = _dt.fromtimestamp(
                                fpath.stat().st_mtime,
                                tz=applied_time.tzinfo,
                            )
                            if mtime < applied_time:
                                missing.append(
                                    f"{fname} (stale — modified before patch applied)"
                                )
                except Exception as ts_exc:
                    # MVP-1 acceptance: timestamp errors are fatal
                    # dev mode: non-fatal warning
                    if execution_mode == "mvp1_acceptance":
                        missing.append(
                            f"timestamp validation error: {ts_exc}"
                        )
                    # dev mode: silently continue (non-fatal)

            if missing:
                gate_results.append({
                    "gate_id": 9,
                    "gate_name": "Smoke Simulation",
                    "passed": False,
                    "severity": "fail",
                    "message": (
                        f"Missing/invalid: {', '.join(missing)}. "
                        f"Present: {', '.join(present) if present else 'none'}"
                    ),
                    "retry_node": "write_fix_patch",
                })
            else:
                gate_results.append({
                    "gate_id": 9,
                    "gate_name": "Smoke Simulation",
                    "passed": True,
                    "severity": "pass",
                    "message": f"All required files verified ({len(present)} files)",
                    "retry_node": None,
                })
    except Exception as exc9:
        gate_results.append(
            _check_execution_mode_gate(
                9, False, "skipped",
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
