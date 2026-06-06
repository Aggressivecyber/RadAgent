"""Generate final simulation report."""

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
    rag_route = state.get("rag_route", [])
    rag_score = state.get("rag_sufficiency_score", 0.0)
    rag_report = state.get("rag_sufficiency_report", {})
    patch = state.get("proposed_patch", {})
    gate_results = state.get("gate_results", [])
    sim_results = state.get("simulation_results", {})
    contract_results = state.get("data_contract_results", {})
    failure = state.get("failure_report", {})

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
        "## 3. RAG Sources Used",
        "",
        f"- Routes: {', '.join(rag_route) if rag_route else 'None'}",
        f"- Sufficiency Score: {rag_score:.2f}",
        f"- Decision: {rag_report.get('decision', 'unknown')}",
        "",
        "## 4. Code Generation",
        "",
        f"- Patch ID: {patch.get('patch_id', 'N/A')}",
        f"- Description: {patch.get('description', 'N/A')}",
        f"- Files Generated: {len(patch.get('changed_files', []))}",
        f"- Risk Level: {patch.get('risk_level', 'N/A')}",
        "",
        "## 5. Gate Results",
        "",
    ]

    for g in gate_results:
        status = "PASS" if g.get("passed") else "FAIL"
        lines.append(
            f"- Gate {g.get('gate_id')}: {g.get('gate_name')} -- {status} {g.get('message', '')}"
        )

    lines.extend(["", "## 6. Simulation Results", ""])

    if sim_results.get("geant4"):
        g4 = sim_results["geant4"]
        lines.append("### Geant4 Output")
        lines.append(f"- Output exists: {g4.get('output_exists', False)}")
        for name, info in g4.get("outputs", {}).items():
            lines.append(f"- {name}: {info.get('file')} (exists: {info.get('exists', False)})")
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

    lines.extend(["", "## 9. Known Issues and Next Steps", ""])

    issues = []
    if rag_score < 0.75:
        issues.append("- RAG context was insufficient; consider expanding the knowledge base")
    if not all(g.get("passed") for g in gate_results):
        issues.append("- Some gates failed; review failure report above")
    if sim_results.get("geant4", {}).get("output_exists") is False:
        issues.append("- Geant4 output does not exist; simulation may not have run")

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
