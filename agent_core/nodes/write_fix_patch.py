"""Generate fix patch based on failure analysis.

Fix 7: Actually attempts LLM-based code fix instead of copying the original patch.
"""

from __future__ import annotations

import json
import logging
import uuid

from agent_core.config.workspace import get_output_dir
from agent_core.graph.state import RadiationAgentState

logger = logging.getLogger(__name__)

FIX_PROMPT = """You are fixing a Geant4 simulation code issue.

The previous code generation failed at gate "{gate_name}" with this error:
{error_message}

Previous code files:
{previous_files}

Error context from RAG:
{error_context}

Generate a COMPLETE, corrected Geant4 project. Output a JSON object:
{{
  "files": {{
    "DetectorConstruction.cc": "corrected content",
    ...
  }},
  "description": "Fix for {gate_name}",
  "assumptions": ["what was fixed"]
}}

Use bare filenames (no directory prefixes). Return ONLY the JSON object.
"""


async def write_fix_patch(state: RadiationAgentState) -> dict:
    """Generate a fix patch based on the failure report and error context."""
    failure = state.get("failure_report", {})
    job_id = state.get("job_id", "unknown")
    original_patch = state.get("proposed_patch", {})
    error_context = state.get("rag_error_context", [])
    g4_context = state.get("g4_context", [])

    gate_name = failure.get("gate_name", "unknown")
    error_msg = failure.get("message", "Unknown error")

    # Build summary of previous files for context
    prev_files = original_patch.get("changed_files", [])
    prev_summary = "\n".join(
        f"- {f.get('path', '?')} ({len(f.get('new_content', ''))} chars)"
        for f in prev_files[:10]
    )

    error_ctx_str = (
        json.dumps((error_context + g4_context)[:5], indent=2, ensure_ascii=False)
        if (error_context or g4_context)
        else "No additional context available"
    )

    # Attempt LLM-based fix
    code_result: dict | None = None
    try:
        from agent_core.llm import get_llm

        llm = get_llm(temperature=0)
        prompt = FIX_PROMPT.format(
            gate_name=gate_name,
            error_message=error_msg,
            previous_files=prev_summary,
            error_context=error_ctx_str,
        )
        response = await llm.ainvoke(prompt)
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        code_result = json.loads(content.strip())
    except Exception as exc:
        logger.warning("LLM fix generation failed: %s", exc)

    if not code_result or not code_result.get("files"):
        # Fix 7: Return empty fix → will exhaust retries and generate failure report
        return {
            "fix_patch": {
                "patch_id": str(uuid.uuid4()),
                "job_id": job_id,
                "description": f"Fix attempt failed for {gate_name}",
                "change_type": "modify",
                "risk_level": "medium",
                "changed_files": [],
                "fix_reason": f"LLM fix generation failed: {error_msg}",
                "test_plan": state.get("test_plan", {}).get("tests", []),
                "expected_outputs": [
                    "g4_summary.json", "edep_3d.csv", "dose_3d.csv",
                    "event_table.csv", "provenance.json",
                ],
                "dependencies": ["Geant4"],
                "rollback_possible": True,
            },
            "current_node": "write_fix_patch",
        }

    # Build fix patch with same layout mapping as write_code_patch
    from agent_core.nodes.write_code_patch import _map_to_geant4_layout

    files = code_result.get("files", {})
    fix_patch = {
        "patch_id": str(uuid.uuid4()),
        "job_id": job_id,
        "description": code_result.get("description", f"Fix for {gate_name}"),
        "change_type": "modify",
        "risk_level": "medium",
        "changed_files": _map_to_geant4_layout(files),
        "fix_reason": error_msg,
        "output_dir": str(get_output_dir(job_id)),
        "test_plan": state.get("test_plan", {}).get("tests", []),
        "expected_outputs": [
            "g4_summary.json", "edep_3d.csv", "dose_3d.csv",
            "event_table.csv", "provenance.json",
        ],
        "dependencies": ["Geant4"],
        "rollback_possible": True,
    }

    return {
        "fix_patch": fix_patch,
        "proposed_patch": fix_patch,  # Update proposed_patch so apply_patch can use it
        "current_node": "write_fix_patch",
    }
