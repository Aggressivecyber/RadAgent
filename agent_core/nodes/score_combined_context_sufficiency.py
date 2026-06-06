"""Score combined RAG + Web context sufficiency.

Decision matrix:
  RAG allow_rag                          -> allow_rag
  RAG needs_web  + Web meets criteria    -> allow_with_web_supplement
  RAG needs_web  + Web insufficient      -> block_no_context
  RAG block_no_context                   -> block_no_context

Web supplement criteria (ALL must pass):
  1. At least 2 valid URLs
  2. At least 1 URL from official/doc/vendor domain
  3. At least 1 title/snippet hits required source keywords
  4. context_sufficiency_report records used_for per URL

Saves context_sufficiency_report.json with provenance details.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from agent_core.config.workspace import get_job_dir
from agent_core.graph.state import RadiationAgentState

_WEB_SUPPLEMENT_MIN_SCORE = 0.30  # Need at least some web results
_MIN_WEB_URLS = 2

# Domains considered official/documentation/vendor sources
_OFFICIAL_DOMAINS = {
    "cern.ch", "geant4.org", "root.cern",
    "github.com", "docs.python.org",
    "anysilicon.com", "synopsys.com", "cadence.com",
    "si2.org", "ieee.org", "arxiv.org",
    "wikipedia.org", "ngspice.org",
}


def _is_official_source(url: str) -> bool:
    """Check if URL is from an official/documentation/vendor domain."""
    lower = url.lower()
    return any(domain in lower for domain in _OFFICIAL_DOMAINS)


def _keyword_hits(title: str, snippet: str, keywords: list[str]) -> bool:
    """Check if title or snippet hits at least one required keyword."""
    combined = f"{title} {snippet}".lower()
    return any(kw.lower() in combined for kw in keywords)


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
    rag_required = state.get("rag_required_sources", [])

    # Build required keywords from RAG required sources
    required_keywords = rag_required + ["simulation", "physics"]

    # Determine final decision
    if rag_decision == "allow_rag":
        final_decision = "allow_rag"
        combined_score = rag_score
        web_fail_reason = ""
    elif rag_decision == "needs_web" and web_available and web_context:
        # Evaluate web supplement criteria
        urls = [r.get("url", "") for r in web_context if r.get("url")]
        has_enough_urls = len(urls) >= _MIN_WEB_URLS
        has_official = any(_is_official_source(u) for u in urls)
        has_keyword_hit = any(
            _keyword_hits(
                r.get("title", ""),
                r.get("snippet", ""),
                required_keywords,
            )
            for r in web_context
        )

        if (
            web_score >= _WEB_SUPPLEMENT_MIN_SCORE
            and has_enough_urls
            and has_official
            and has_keyword_hit
        ):
            final_decision = "allow_with_web_supplement"
            combined_score = max(rag_score, 0.75)
            web_fail_reason = ""
        else:
            reasons = []
            if not has_enough_urls:
                reasons.append(f"<{_MIN_WEB_URLS} valid URLs ({len(urls)})")
            if not has_official:
                reasons.append("no official/documentation source")
            if not has_keyword_hit:
                reasons.append("no title/snippet keyword match")
            if web_score < _WEB_SUPPLEMENT_MIN_SCORE:
                reasons.append(f"web score {web_score:.2f} < {_WEB_SUPPLEMENT_MIN_SCORE}")
            web_fail_reason = "; ".join(reasons)
            final_decision = "block_no_context"
            combined_score = rag_score
    elif rag_decision == "needs_web" and not web_available:
        final_decision = "block_no_context"
        combined_score = rag_score
        web_fail_reason = "web search unavailable"
    else:
        final_decision = "block_no_context"
        combined_score = rag_score
        web_fail_reason = ""

    # Build used_for mapping per web result
    used_for_list = []
    for r in web_context:
        url = r.get("url", "")
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        confidence = r.get("confidence", 0.0)
        entry = {
            "url": url,
            "title": title,
            "confidence": confidence,
            "is_official": _is_official_source(url) if url else False,
            "keyword_matches": [
                kw for kw in required_keywords
                if kw.lower() in f"{title} {snippet}".lower()
            ],
            "used_for": (
                "supplement"
                if final_decision == "allow_with_web_supplement"
                else "rejected"
            ),
        }
        used_for_list.append(entry)

    report = {
        "rag_score": rag_score,
        "rag_decision": rag_decision,
        "web_score": round(web_score, 2),
        "web_result_count": len(web_context),
        "web_available": web_available,
        "combined_score": round(combined_score, 2),
        "decision": final_decision,
        "web_fail_reason": web_fail_reason,
        "min_urls_required": _MIN_WEB_URLS,
        "official_source_found": any(
            _is_official_source(r.get("url", ""))
            for r in web_context
        ),
        "keyword_hit_found": any(
            _keyword_hits(
                r.get("title", ""), r.get("snippet", ""), required_keywords
            )
            for r in web_context
        ),
        "required_keywords_checked": required_keywords,
        "used_for": used_for_list,
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
