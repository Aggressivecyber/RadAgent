"""Generate final simulation report with full context disclosure."""

from __future__ import annotations

import json
from datetime import datetime

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState


async def generate_report(state: RadiationAgentState) -> dict:
    """Generate the final simulation report."""
    job_id = state.get("job_id", "unknown")
    user_query = state.get("user_query", "")
    task_spec = state.get("task_spec", {})
    rag_required = state.get("rag_required_sources", [])
    rag_optional = state.get("rag_optional_sources", [])
    rag_score = state.get("rag_sufficiency_score", 0.0)
    rag_report = state.get("rag_sufficiency_report", {})
    patch = state.get("proposed_patch", {})
    gate_results = state.get("gate_results", [])
    sim_results = state.get("simulation_results", {})
    contract_results = state.get("data_contract_results", {})
    failure = state.get("failure_report", {})
    execution_mode = state.get("execution_mode", "dev_no_geant4_env")
    skipped_gates = state.get("skipped_gates", [])
    context_decision = state.get("context_decision", "block_no_context")
    web_context = state.get("web_context", [])

    # Build report sections
    lines = [
        f"# Simulation Report: {job_id}",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
        "## 1. User Request",
        "",
        user_query,
        "",
        "## 2. Task Specification",
        "",
        "```json",
        json.dumps(task_spec, indent=2, ensure_ascii=False),
        "```",
        "",
        "## 3. Context Sources",
        "",
        f"- Required RAG sources: {', '.join(rag_required) if rag_required else 'None'}",
        f"- Optional RAG sources: {', '.join(rag_optional) if rag_optional else 'None'}",
        f"- RAG sufficiency score: {rag_score:.2f}",
        f"- RAG decision: {rag_report.get('decision', 'unknown')}",
        f"- Final context decision: {context_decision}",
    ]

    # RAG source detail
    g4_count = len(state.get("g4_context", []))
    tcad_count = len(state.get("tcad_context", []))
    spice_count = len(state.get("spice_context", []))
    lines.append(f"- Geant4 context entries: {g4_count}")
    lines.append(f"- TCAD context entries: {tcad_count}")
    lines.append(f"- SPICE context entries: {spice_count}")

    # Web context detail
    if web_context:
        lines.append(f"- Web sources used: {len(web_context)} results")
        urls = sorted(set(r.get("url", "") for r in web_context if r.get("url")))
        for u in urls[:5]:
            lines.append(f"  - {u}")
        if len(urls) > 5:
            lines.append(f"  - ... and {len(urls) - 5} more")
    else:
        lines.append("- Web sources: none used")

    # Context provenance for web-supplemented
    if context_decision == "allow_with_web_supplement":
        lines.append("")
        lines.append("**⚠️ Context includes web-supplemented information — verify independently.**")

    lines.extend(["", "## 4. Code Generation", ""])
    lines.append(f"- Patch ID: {patch.get('patch_id', 'N/A')}")
    lines.append(f"- Description: {patch.get('description', 'N/A')}")
    lines.append(f"- Files Generated: {len(patch.get('changed_files', []))}")
    lines.append(f"- Risk Level: {patch.get('risk_level', 'N/A')}")

    lines.extend(["", "## 5. Gate Results", ""])

    passed_count = sum(1 for g in gate_results if g.get("passed"))
    for g in gate_results:
        status = "PASS" if g.get("passed") else "FAIL"
        sev = g.get("severity", "")
        if sev == "skipped":
            status = "SKIPPED"
        elif sev == "warning":
            status = "PASS (with warning)"
        elif sev == "block":
            status = "BLOCKED"
        lines.append(
            f"- Gate {g.get('gate_id')}: {g.get('gate_name')} -- {status} {g.get('message', '')}"
        )

    lines.append(f"\nGate Summary: {passed_count}/{len(gate_results)} passed")

    lines.extend(["", "## 6. Simulation Results", ""])

    if sim_results.get("geant4"):
        g4 = sim_results["geant4"]
        lines.append("### Geant4 Output")
        lines.append(f"- All required files present: {g4.get('all_required_files_present', False)}")
        for name, info in g4.get("outputs", {}).items():
            lines.append(
                f"- {name}: {info.get('file')} "
                f"(exists: {info.get('exists', False)}, rows: {info.get('rows', 0)})"
            )
    else:
        lines.append("No simulation results available.")

    lines.extend(["", "## 7. Data Contract Validation", ""])

    for contract_name, result in contract_results.items():
        status = "PASS" if result.get("valid") else "FAIL"
        lines.append(f"- {contract_name}: {status}")
        for err in result.get("errors", []):
            lines.append(f"  - {err}")

    lines.extend(["", "## 8. Failure Report", ""])

    if failure.get("type") and failure["type"] != "none":
        lines.append(f"- Type: {failure.get('type')}")
        lines.append(f"- Gate: {failure.get('gate_name')} (ID: {failure.get('gate_id')})")
        lines.append(f"- Message: {failure.get('message')}")
        lines.append(f"- Retries: {failure.get('total_retries', 0)}")
    else:
        lines.append("No failures detected.")

    # --- Execution Mode Section ---
    lines.extend(["", "## 9. Execution Mode", ""])
    if execution_mode == "mvp1_acceptance":
        lines.append("**Mode: MVP-1 Acceptance** — All gates enforced, no skips allowed.")
    else:
        lines.append(
            "**Mode: Dev (No Geant4 Environment)** — "
            "Critical gates may be skipped. **NOT MVP-1 VERIFIED.**"
        )

    # --- Skipped Gates Section ---
    if skipped_gates:
        lines.extend(["", "## 10. Skipped Gates", ""])
        for sg in skipped_gates:
            gid = sg.get("gate_id", "?")
            reason = sg.get("reason", "Unknown")
            lines.append(f"- Gate {gid}: {reason}")
            if execution_mode == "dev_no_geant4_env":
                lines.append("  - [DEV MODE ONLY — would fail in acceptance mode]")

    # --- MVP-1 Status ---
    lines.extend(["", "## 11. MVP-1 Verification Status", ""])
    has_hard_failure = any(
        g.get("severity") in ("fail", "block") for g in gate_results
    )
    critical_skipped = [
        g for g in gate_results
        if g.get("severity") == "skipped" and g.get("gate_id") in (6, 8, 9, 11)
    ]

    if execution_mode == "mvp1_acceptance":
        if critical_skipped:
            lines.append(
                "**MVP-1: FAILED** — Critical gates were skipped in acceptance mode."
            )
        elif has_hard_failure:
            lines.append("**MVP-1: FAILED** — Gate failures in acceptance mode.")
        else:
            lines.append("**MVP-1: PASSED** — All gates passed in acceptance mode.")
    else:
        lines.append(
            "**MVP-1: NOT VERIFIED** — Running in dev mode (Geant4 not available). "
            "Cannot claim MVP-1 acceptance."
        )

    # --- Termination Reason ---
    if context_decision == "block_no_context":
        lines.extend(["", "## 12. Termination Reason", ""])
        lines.append("Pipeline terminated due to insufficient context.")
        lines.append(f"- RAG score: {rag_score:.2f}")
        lines.append(f"- Web search available: {state.get('web_search_available', False)}")
        lines.append("- Cannot safely generate simulation code without domain context.")
        lines.append("- Either expand the knowledge base or provide web search access.")

    # --- MVP-1 Scope Declaration ---
    task_spec = state.get("task_spec", {})
    simulation_scope = task_spec.get("simulation_scope", ["geant4"])
    non_geant4 = [s for s in simulation_scope if s not in ("geant4",)]
    if non_geant4:
        lines.extend(["", "## 13. MVP-1 Scope Declaration", ""])
        lines.append(
            f"**TCAD/SPICE Reserved for Later MVPs.** "
            f"The following simulation scopes were requested but are not supported in MVP-1: "
            f"{', '.join(non_geant4)}. "
            "RAG retrieval and reporting were allowed, "
            "but no code was generated for these scopes. "
            f"TCAD support is planned for MVP-4, SPICE support for MVP-6."
        )
    else:
        lines.extend(["", "## 13. MVP-1 Scope", ""])
        lines.append("Simulation scope: Geant4 only (MVP-1).")

    lines.extend(["", "## 14. Known Issues and Next Steps", ""])

    issues = []
    if rag_score < 0.75:
        issues.append("- RAG context was insufficient; consider expanding the knowledge base")
    if has_hard_failure:
        issues.append("- Some gates failed; review failure report above")
    if critical_skipped:
        issues.append("- Critical gates were skipped; results not verified")
    if not sim_results.get("geant4", {}).get("all_required_files_present", False):
        issues.append("- Geant4 output files incomplete; simulation may not have run")

    if issues:
        lines.extend(issues)
    else:
        lines.append("No known issues. Simulation completed successfully.")

    report_text = "\n".join(lines)

    # Save report
    job_dir = get_job_dir(job_id)
    report_file = job_dir / "10_report" / "final_report.md"
    report_file.write_text(report_text)

    return {"final_report": report_text, "current_node": "generate_report"}
