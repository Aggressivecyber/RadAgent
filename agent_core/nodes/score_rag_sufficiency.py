"""Score RAG context sufficiency."""

from __future__ import annotations

import json

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState


def _compute_score(
    g4_ctx: list, tcad_ctx: list, spice_ctx: list,
    required_sources: list[str] | None = None,
    optional_sources: list[str] | None = None,
) -> tuple[float, dict]:
    """Compute RAG sufficiency score based on retrieved context.

    *required_sources* and *optional_sources* use logical names ("geant4",
    "tcad", "spice").  If a required source has empty context the score is
    capped below the block threshold (0.60).
    """
    required_sources = required_sources or []
    optional_sources = optional_sources or []

    score = 0.0
    report: dict = {
        "missing_items": [],
        "has_manual": False,
        "has_examples": False,
        "has_contracts": False,
    }

    # Map logical names to their context lists
    _ctx_map: dict[str, list] = {
        "geant4": g4_ctx,
        "tcad": tcad_ctx,
        "spice": spice_ctx,
    }

    # --- Required-source penalty -------------------------------------------
    missing_required: list[str] = []
    for src in required_sources:
        if src in _ctx_map and not _ctx_map[src]:
            missing_required.append(src)
    if missing_required:
        report["missing_required_sources"] = missing_required
        for ms in missing_required:
            report["missing_items"].append(
                f"Required source '{ms}' returned no context"
            )

    all_ctx = g4_ctx + tcad_ctx + spice_ctx

    if not all_ctx:
        report["missing_items"] = ["No context retrieved at all"]
        return 0.0, report

    # Check for manual snippets
    has_manual = any(
        ctx.get("source_type") == "manual"
        or "manual" in ctx.get("source", "").lower()
        for ctx in all_ctx
    )
    if has_manual:
        score += 0.30
        report["has_manual"] = True
    else:
        report["missing_items"].append("No manual snippets found")

    # Check for example code
    has_examples = any(
        "code" in ctx.get("source", "").lower()
        or ctx.get("doc_type") == "example_code"
        for ctx in all_ctx
    )
    if has_examples:
        score += 0.25
        report["has_examples"] = True
    else:
        report["missing_items"].append("No example code found")

    # Check for data contracts
    has_contracts = any(
        "contract" in ctx.get("source", "").lower() for ctx in all_ctx
    )
    if has_contracts:
        score += 0.20
        report["has_contracts"] = True
    else:
        report["missing_items"].append("No data contract info found")

    # Base score for having any context
    if len(all_ctx) > 0:
        score += 0.15

    # --- Cap score if a required source is empty ---------------------------
    if missing_required:
        score = min(score, 0.55)

    # Decision
    if score >= 0.90:
        report["decision"] = "allow"
    elif score >= 0.75:
        report["decision"] = "allow_with_warning"
    elif score >= 0.60:
        report["decision"] = "allow_draft_only"
    else:
        report["decision"] = "block"

    report["score"] = round(max(0.0, score), 2)
    return report["score"], report


async def score_rag_sufficiency(state: RadiationAgentState) -> dict:
    """Score the sufficiency of retrieved RAG context.

    When no RAG server is available (all contexts empty), gives a baseline
    score of 0.76 with a warning so the pipeline can proceed using the
    LLM's built-in knowledge as fallback.
    """
    g4_ctx = state.get("g4_context", [])
    tcad_ctx = state.get("tcad_context", [])
    spice_ctx = state.get("spice_context", [])
    rag_required = state.get("rag_required_sources", [])
    rag_optional = state.get("rag_optional_sources", [])
    job_id = state.get("job_id", "unknown")

    score, report = _compute_score(
        g4_ctx, tcad_ctx, spice_ctx,
        required_sources=rag_required,
        optional_sources=rag_optional,
    )

    # When no RAG server is available, allow pipeline to proceed with warning
    if score == 0.0:
        score = 0.76
        report["score"] = 0.76
        report["decision"] = "allow_with_warning"
        report["missing_items"].insert(
            0, "WARNING: No RAG server available, proceeding with LLM knowledge only"
        )

    # Save report
    job_dir = get_job_dir(job_id)
    report_file = job_dir / "01_context" / "rag_sufficiency_report.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return {
        "rag_sufficiency_score": score,
        "rag_sufficiency_report": report,
        "current_node": "score_rag_sufficiency",
    }
