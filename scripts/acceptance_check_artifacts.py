#!/usr/bin/env python3
"""Acceptance check for g4_complex_model/latest artifacts.

Runs all P0 checks from phases 3-10 of the bf36d95 acceptance directive.
Exit 0 on PASS, exit 1 on any failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / "review_artifacts" / "g4_complex_model" / "latest"
OUTPUT_DIR = ARTIFACT_DIR / "output"

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not condition:
        FAILURES.append(f"{name}: {detail}")


def main() -> None:
    print("=== Artifact Acceptance Check ===\n")

    # ── P0-1: g4_model_ir 9 components ───────────────────────────────
    print("P0-1: g4_model_ir.json")
    ir_path = OUTPUT_DIR / "g4_model_ir.json"
    check("file exists", ir_path.exists())
    ir = json.loads(ir_path.read_text()) if ir_path.exists() else {}
    ids = [c.get("component_id", "?") for c in ir.get("components", [])]
    required_comps = [
        "world", "housing", "pcb", "sensor_stack", "top_electrode",
        "oxide_layer", "silicon_bulk", "sensitive_region", "bottom_electrode",
    ]
    for comp in required_comps:
        check(f"  component '{comp}'", comp in ids, str(ids))
    check("  components count = 9", len(ids) == 9, f"got {len(ids)}")
    check("  materials count = 5", len(ir.get("materials", [])) == 5, str(ir.get("materials")))
    check("  sources count >= 1", len(ir.get("sources", [])) >= 1, str(ir.get("sources")))
    check("  scoring count = 4", len(ir.get("scoring", [])) == 4, str(ir.get("scoring")))

    # ── P0-10: 10 MeV proton ─────────────────────────────────────────
    src = ir.get("sources", [{}])[0] if ir.get("sources") else {}
    check("  source is proton", "proton" in str(src.get("particle_type", "")).lower(), str(src))
    check("  energy is 10 MeV", "10" in str(src.get("energy", "")), str(src.get("energy")))

    # ── P0-2: component_specs_summary ────────────────────────────────
    print("\nP0-2: component_specs_summary.json")
    sum_path = OUTPUT_DIR / "component_specs_summary.json"
    check("file exists", sum_path.exists())
    summary = json.loads(sum_path.read_text()) if sum_path.exists() else {}
    check("  total_components = 9", summary.get("total_components") == 9, str(summary.get("total_components")))
    sum_ids = summary.get("component_ids", [])
    for comp in ["housing", "pcb", "oxide_layer", "silicon_bulk", "sensitive_region", "bottom_electrode"]:
        check(f"  has '{comp}'", comp in sum_ids, str(sum_ids))
    check("  materials_count = 5", summary.get("materials_count") == 5, str(summary.get("materials_count")))
    check("  scoring_count = 4", summary.get("scoring_count") == 4, str(summary.get("scoring_count")))

    # ── P0-3: confirmation_record ─────────────────────────────────────
    print("\nP0-3: confirmation_record.json")
    rec_path = OUTPUT_DIR / "confirmation_record.json"
    check("file exists", rec_path.exists())
    check("  size > 100 bytes", rec_path.exists() and rec_path.stat().st_size > 100,
          f"{rec_path.stat().st_size if rec_path.exists() else 0} bytes")
    record = json.loads(rec_path.read_text()) if rec_path.exists() else {}
    for key in ["schema_version", "job_id", "total_rounds", "final_status",
                "confirmed_fields", "edited_fields", "rejected_fields",
                "remaining_unconfirmed_fields", "confirmation_history",
                "confirmed_model_plan_path"]:
        check(f"  has '{key}'", key in record, f"keys: {list(record.keys())}")
    if "schema_version" in record:
        check("  schema_version = confirmation_record_v1",
              record["schema_version"] == "confirmation_record_v1", record["schema_version"])
    if "final_status" in record:
        check("  final_status is approved/edited",
              record["final_status"] in {"approved", "edited"}, record["final_status"])
    if "remaining_unconfirmed_fields" in record:
        check("  remaining_unconfirmed_fields empty",
              record["remaining_unconfirmed_fields"] == [], str(record["remaining_unconfirmed_fields"]))
    if "confirmation_history" in record:
        check("  confirmation_history >= 1 round",
              len(record["confirmation_history"]) >= 1, str(len(record["confirmation_history"])))

    # ── P0-4: confirmed_model_plan ────────────────────────────────────
    print("\nP0-4: confirmed_model_plan.json")
    plan_path = OUTPUT_DIR / "confirmed_model_plan.json"
    check("file exists", plan_path.exists())
    check("  size > 100 bytes", plan_path.exists() and plan_path.stat().st_size > 100,
          f"{plan_path.stat().st_size if plan_path.exists() else 0} bytes")
    plan = json.loads(plan_path.read_text()) if plan_path.exists() else {}
    for key in ["schema_version", "confirmation_status", "components",
                "materials", "sources", "scoring", "confirmed_fields",
                "edited_fields", "assumptions", "remaining_unconfirmed_fields"]:
        check(f"  has '{key}'", key in plan, f"keys: {list(plan.keys())}")
    if "components" in plan:
        check("  components count = 9", len(plan["components"]) == 9, str(len(plan["components"])))
    if "materials" in plan:
        check("  materials count = 5", len(plan["materials"]) == 5, str(len(plan["materials"])))
    if "scoring" in plan:
        check("  scoring count = 4", len(plan["scoring"]) == 4, str(len(plan["scoring"])))
    if "remaining_unconfirmed_fields" in plan:
        check("  remaining_unconfirmed_fields empty",
              plan["remaining_unconfirmed_fields"] == [], str(plan["remaining_unconfirmed_fields"]))

    # ── P0-5: human_confirmation_report ───────────────────────────────
    print("\nP0-5: human_confirmation_report.md")
    rep_path = OUTPUT_DIR / "human_confirmation_report.md"
    check("file exists", rep_path.exists())
    text = rep_path.read_text() if rep_path.exists() else ""
    check("  length > 300", len(text) > 300, f"{len(text)} chars")
    for section in ["Summary", "Round 1 Questions", "User Response",
                     "Confirmed Fields", "Edited Fields",
                     "Remaining Unconfirmed Fields", "Final Status"]:
        check(f"  has section '{section}'", section in text)

    # ── P0-6: gate_results G4-H ──────────────────────────────────────
    print("\nP0-6: gate_results.json G4-H")
    gates_path = OUTPUT_DIR / "gate_results.json"
    check("file exists", gates_path.exists())
    gates = json.loads(gates_path.read_text()) if gates_path.exists() else []
    g4h = [g for g in gates if g.get("gate_id") in {19, "G4-H"}
           or "Human Confirmation" in g.get("name", "")]
    check("  G4-H exists", len(g4h) > 0, f"gate_ids: {[g.get('gate_id') for g in gates]}")
    if g4h:
        g = g4h[0]
        check("  status = pass", g.get("status") == "pass", g.get("status"))
        check("  checked_items >= 4", len(g.get("checked_items", [])) >= 4,
              str(len(g.get("checked_items", []))))
        check("  passed_items non-empty", len(g.get("passed_items", [])) >= 4,
              str(len(g.get("passed_items", []))))
        check("  failed_items empty", g.get("failed_items") == [], str(g.get("failed_items")))
        check("  file_paths non-empty", bool(g.get("file_paths")), str(g.get("file_paths")))
        check("  mentions confirmation_record",
              "confirmation_record" in str(g), str(g)[:200])
        check("  mentions confirmed_model_plan",
              "confirmed_model_plan" in str(g), str(g)[:200])

    # ── P0-7: review_report ──────────────────────────────────────────
    print("\nP0-7: review_report.json")
    rev_path = ARTIFACT_DIR / "review_report.json"
    check("file exists", rev_path.exists())
    review = json.loads(rev_path.read_text()) if rev_path.exists() else {}
    check("  run_type = dev", review.get("run_type") == "dev", review.get("run_type"))
    check("  validation_status != VERIFIED",
          review.get("validation_status") != "VERIFIED", review.get("validation_status"))
    check("  is_stub = false", review.get("is_stub") is False, str(review.get("is_stub")))
    check("  has_human_confirmation = true",
          review.get("has_human_confirmation") is True, str(review.get("has_human_confirmation")))
    hc = review.get("human_confirmation", {})
    check("  hc.required = true", hc.get("required") is True, str(hc.get("required")))
    check("  hc.status in approved/edited",
          hc.get("status") in {"approved", "edited"}, str(hc.get("status")))
    check("  hc.rounds >= 1", hc.get("rounds", 0) >= 1, str(hc.get("rounds")))
    check("  hc.remaining_unconfirmed_fields empty",
          hc.get("remaining_unconfirmed_fields") == [], str(hc.get("remaining_unconfirmed_fields")))

    # ── P0-8: artifact_manifest source_commit ─────────────────────────
    print("\nP0-8+9: artifact_manifest.json")
    man_path = ARTIFACT_DIR / "artifact_manifest.json"
    check("file exists", man_path.exists())
    manifest = json.loads(man_path.read_text()) if man_path.exists() else {}
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        head = ""
    mc = manifest.get("source_commit", "")
    check("  source_commit = HEAD",
          head and (mc == head or head.startswith(mc)),
          f"manifest={mc}, HEAD={head}")
    check("  validation_status != VERIFIED",
          manifest.get("validation_status") != "VERIFIED", manifest.get("validation_status"))
    check("  run_type = dev", manifest.get("run_type") == "dev", manifest.get("run_type"))
    check("  is_stub = false", manifest.get("is_stub") is False, str(manifest.get("is_stub")))
    ms = manifest.get("model_ir_summary", {})
    ms_ids = [c.get("component_id") for c in ms.get("components", [])]
    for comp in ["housing", "pcb", "oxide_layer", "silicon_bulk", "sensitive_region", "bottom_electrode"]:
        check(f"  summary has '{comp}'", comp in ms_ids, str(ms_ids))
    check("  summary materials_count = 5", ms.get("materials_count") == 5, str(ms.get("materials_count")))
    check("  summary scoring_count = 4", ms.get("scoring_count") == 4, str(ms.get("scoring_count")))
    mf_names = [f.get("name", "") for f in manifest.get("files", [])]
    for f in ["confirmation_record.json", "confirmed_model_plan.json", "human_confirmation_report.md"]:
        check(f"  files contains '{f}'", f in mf_names, str(mf_names))

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 40}")
    if FAILURES:
        print(f"FAIL — {len(FAILURES)} issue(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("PASS — All artifact checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
