"""Score combined RAG + Web context sufficiency.

Decision matrix:
  RAG allow_rag                          -> allow_rag
  RAG needs_web  + Web score >= 0.30     -> allow_with_web_supplement
  RAG needs_web  + Web unavailable       -> block_no_context
  RAG block_no_context                   -> block_no_context

Saves context_sufficiency_report.json with provenance details.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState

_WEB_SUPPLEMENT_MIN_SCORE = 0.30  # Need at least some web results


async def score_combined_context_sufficiency(
    state: RadiationAgentState,
) -> dict:
    """Combine RAG and Web scores into a final context decision."""
    rag_score = state.get("rag_sufficiency_score", 0.0)
    rag_decision = state.get("context_decision", "block_no_context")
    web_score = state.get("web_sufficiency_score", 0.0)
    web_context = state.get("web_context", [])
    web_available = state.get("web_search_available", False)
    job_id = state.get("job_id", "unknown")

    # Determine final decision
    if rag_decision == "allow_rag":
        final_decision = "allow_rag"
        combined_score = rag_score
    elif (
        rag_decision == "needs_web"
        and web_score >= _WEB_SUPPLEMENT_MIN_SCORE
        and web_context
    ):
        final_decision = "allow_with_web_supplement"
        combined_score = max(rag_score, 0.75)
    elif rag_decision == "needs_web" and not web_available:
        final_decision = "block_no_context"
        combined_score = rag_score
    else:
        final_decision = "block_no_context"
        combined_score = rag_score

    report = {
        "rag_score": rag_score,
        "rag_decision": rag_decision,
        "web_score": round(web_score, 2),
        "web_result_count": len(web_context),
        "web_available": web_available,
        "combined_score": round(combined_score, 2),
        "decision": final_decision,
        "timestamp": datetime.now(UTC).isoformat(),
        "web_urls": sorted(
            set(r.get("url", "") for r in web_context if r.get("url"))
        ),
    }

    # Save report
    job_dir = get_job_dir(job_id)
    report_file = job_dir / "01_context" / "context_sufficiency_report.json"
    report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return {
        "context_decision": final_decision,
        "context_sufficiency_report": report,
        "current_node": "score_combined_context_sufficiency",
    }
