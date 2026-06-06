"""Run all gate checks on the generated code."""

from __future__ import annotations

import json
from pathlib import Path

from agent_core.graph.state import RadiationAgentState
from agent_core.validators.code_structure_validator import CodeStructureValidator
from agent_core.validators.file_permission_validator import FilePermissionValidator
from agent_core.validators.patch_validator import PatchValidator
from agent_core.validators.schema_validator import SchemaValidator


async def run_gate_checks(state: RadiationAgentState) -> dict:
    """Run all 12 gate checks sequentially."""
    gate_results = []
    job_id = state.get("job_id", "unknown")
    patch = state.get("proposed_patch", {})
    task_spec = state.get("task_spec", {})
    sim_ir = state.get("simulation_ir", {})
    rag_score = state.get("rag_sufficiency_score", 0.0)

    # Gate 0: RAG Sufficiency
    g0_passed = rag_score >= 0.75
    gate_results.append(
        {
            "gate_id": 0,
            "gate_name": "RAG Sufficiency",
            "passed": g0_passed,
            "severity": "pass" if g0_passed else "fail",
            "message": f"RAG score: {rag_score:.2f}",
            "retry_node": "retrieve_g4_context" if not g0_passed else None,
        }
    )

    # Gate 1: Task Spec Schema
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

    # Gate 2: Simulation IR Schema
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

    # Gate 3: Patch Format
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

    # Gate 4: File Permission
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

    # Gate 5: Static Check (structure validation)
    job_dir = Path("simulation_workspace/jobs") / job_id
    g4_dir = job_dir / "05_geant4"
    csv = CodeStructureValidator()
    struct_valid, struct_errors = csv.validate_geant4_project(str(g4_dir))
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

    # Gate 6: Build (attempt if Geant4 available)
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
            build_msg = f"Structure check (Geant4 not available): {'OK' if build_valid else 'Issues found'}"
    except Exception as e:
        build_valid = False
        build_msg = f"Build check error: {e}"

    gate_results.append(
        {
            "gate_id": 6,
            "gate_name": "Build/Parse",
            "passed": build_valid,
            "severity": "pass" if build_valid else "fail",
            "message": build_msg,
            "retry_node": "write_fix_patch" if not build_valid else None,
        }
    )

    # Gates 7-11: Stubs for MVP-1 (pass by default)
    gate_names = {
        7: "Unit Test",
        8: "Data Contract",
        9: "Smoke Simulation",
        10: "Benchmark Regression",
        11: "Physics Sanity",
    }
    for gate_id in range(7, 12):
        gate_results.append(
            {
                "gate_id": gate_id,
                "gate_name": gate_names[gate_id],
                "passed": True,
                "severity": "pass",
                "message": "MVP-1: Auto-pass (will be implemented in later MVPs)",
                "retry_node": None,
            }
        )

    # Save gate results
    gate_file = job_dir / "09_validation" / "gate_results.json"
    gate_file.write_text(json.dumps(gate_results, indent=2, ensure_ascii=False))

    return {
        "gate_results": gate_results,
        "current_node": "run_gate_checks",
        "retry_count": state.get("retry_count", 0),
    }
