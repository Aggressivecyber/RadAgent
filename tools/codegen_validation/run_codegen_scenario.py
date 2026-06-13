"""Direct codegen validation: re-run the g4_codegen subgraph on job_cbb4f07a's IR
with the updated module_context_examples, then audit whether the regenerated
DetectorConstruction creates ScoringManager in the constructor and whether the
smoke deposits non-zero energy. Avoids the flaky textual run_test() harness.
"""
from __future__ import annotations
import asyncio, json, os, sys, tempfile, time, traceback
from pathlib import Path

# Scenario: argv[1] = IR path, argv[2] = scenario name (for result/log naming)
SRC_IR = sys.argv[1] if len(sys.argv) > 1 else "/home/rylan/RadAgent/simulation_workspace/jobs/job_cbb4f07a__20260612_072455/03_model_ir/g4_model_ir.json"
SCENARIO = sys.argv[2] if len(sys.argv) > 2 else "baseline"

WS = Path(os.environ.get("RADAGENT_WORKSPACE_ROOT") or tempfile.mkdtemp(prefix=f"radagent_cv_{SCENARIO}_"))
if not os.environ.get("RADAGENT_WORKSPACE_ROOT"):
    os.environ["RADAGENT_WORKSPACE_ROOT"] = str(WS)
RESULT = Path(f"/tmp/codegen_validate_result_{SCENARIO}.json")

from agent_core.graph.subgraphs.g4_codegen_graph import build_g4_codegen_subgraph


def log(m): print(m, flush=True)


async def main():
    ts = time.strftime("%Y%m%d_%H%M%S")
    job_id = f"codegen_validate_{SCENARIO}_{ts}"
    job_dir = WS / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    log(f"[setup] workspace={WS} job={job_id}")

    state = {
        "job_id": job_id,
        "g4_model_ir_path": SRC_IR,
        "run_mode": "strict",
        "execution_mode": "test",
    }
    graph = build_g4_codegen_subgraph().compile()
    log("[codegen] invoking subgraph (planning + 3 modules + integration repair)...")
    t0 = time.time()
    result = await graph.ainvoke(state)
    log(f"[codegen] done in {time.time()-t0:.0f}s; g4_codegen_status={result.get('g4_codegen_status')}")

    gi = result.get("global_integration_agent_report", {})
    log(f"[codegen] global_integration status={gi.get('status')} turns={gi.get('repair_turns')}")

    integ = job_dir / "05_codegen" / "integration"
    attempts = sorted(integ.glob("runtime_attempt_*"))
    audit = {
        "job_id": job_id,
        "g4_codegen_status": result.get("g4_codegen_status"),
        "global_integration_status": gi.get("status"),
        "n_attempts": len(attempts),
    }

    # Did ANY attempt's smoke pass (build + run + nonzero edep)?
    # Check the canonical gate output (g4_output_package) — that is what the
    # integration gate actually validates; the agent-loop smoke_output is transient.
    audit["any_smoke_passed"] = False
    audit["attempt_smokes"] = []
    for a in attempts:
        sr = a / "g4_output_package" / "smoke_simulation_result.json"
        st = {}
        if sr.is_file():
            try:
                d = json.loads(sr.read_text())
                st = {"attempt": a.name, "success": d.get("success"),
                      "returncode": d.get("returncode")}
                if d.get("success"):
                    audit["any_smoke_passed"] = True
            except Exception:
                st = {"attempt": a.name, "parse_error": True}
        audit["attempt_smokes"].append(st)

    # Check the LATEST attempt's DetectorConstruction for the constructor pattern
    # (the model's actual generation; 06_patch is only written on overall pass).
    det = None
    if attempts:
        det = attempts[-1] / "geant4_project" / "src" / "DetectorConstruction.cc"
    audit["sm_in_constructor_latest"] = False
    audit["sm_in_constructsdandfield_latest"] = False
    if det and det.is_file():
        src = det.read_text()
        audit["sm_in_constructor_latest"] = "fScoringManager(new ScoringManager" in src
        audit["sm_in_constructsdandfield_latest"] = (
            "fScoringManager = new ScoringManager" in src
        )
        log(f"[audit] latest DetectorConstruction: constructor={audit['sm_in_constructor_latest']} "
            f"constructsdandfield={audit['sm_in_constructsdandfield_latest']}")
    else:
        log(f"[audit] no DetectorConstruction.cc found in attempts")

    # Also check attempt_0 (the first, cleanest generation) for pattern adoption.
    if attempts:
        d0 = attempts[0] / "geant4_project" / "src" / "DetectorConstruction.cc"
        if d0.is_file():
            audit["sm_in_constructor_attempt0"] = "fScoringManager(new ScoringManager" in d0.read_text()

    RESULT.write_text(json.dumps(audit, indent=2, ensure_ascii=False))
    log("\n===== CODEGEN VALIDATION RESULT =====\n" + json.dumps(audit, indent=2, ensure_ascii=False))
    # PASS = a smoke actually passed (the real bar for stable production).
    verdict = audit.get("any_smoke_passed")
    log(f"\n[VERDICT] {'PASS' if verdict else 'FAIL'} (a runtime_attempt smoke passed)")
    return 0 if verdict else 5


if __name__ == "__main__":
    try:
        rc = asyncio.run(asyncio.wait_for(main(), timeout=2400))
        sys.exit(rc or 0)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
