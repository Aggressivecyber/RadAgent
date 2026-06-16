from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_TASK_PLAN


REQUIREMENTS_REVIEW_REQUEST = "requirements_review_request.json"
REQUIREMENTS_REVIEW_RESPONSE = "requirements_review_response.json"
CONFIRMED_REQUIREMENT_PLAN = "confirmed_requirement_plan.json"


SYSTEM_PROMPT = """You are RadAgent's pre-codegen Geant4 requirements reviewer.

Review the user's simulation request and extracted task_spec before any Geant4
model IR or C++ code is generated. Use the strongest available model judgment to
find missing, ambiguous, risky, or defaulted parameters that a human should see.

Return JSON only with:
{
  "summary_for_user": "...",
  "missing_information": ["..."],
  "ambiguous_parameters": [{"field_path":"...", "proposed_value":"...", "reason":"..."}],
  "physics_risks": ["..."],
  "questions": [{"field_path":"...", "question":"...", "proposed_value":"..."}],
  "proposed_parameters": [{"field_path":"...", "proposed_value":..., "source_type":"user|model_inferred|default", "confidence":0.0, "requires_confirmation": true}],
  "proposed_defaults": [{"field_path":"...", "proposed_value":..., "reason":"..."}]
}

Focus on particle type, energy/spectrum, source direction/position, materials,
geometry dimensions, layer order, scoring outputs, event count, physics list,
production cuts, step limits, and units.
"""


async def requirements_review_node(state: dict[str, Any]) -> dict[str, Any]:
    job_id = str(state.get("job_id") or "unknown")
    task_spec = _read_json(str(state.get("task_spec_path") or ""))
    review_dir = get_stage_dir(job_id, STAGE_TASK_PLAN)
    review_dir.mkdir(parents=True, exist_ok=True)

    prompt = json.dumps(
        {
            "user_query": state.get("user_query", ""),
            "task_spec": task_spec,
            "context_report_path": state.get("context_report_path", ""),
            "evidence_map_path": state.get("evidence_map_path", ""),
        },
        ensure_ascii=False,
        indent=2,
    )
    gateway = get_model_gateway()
    result = await gateway.call(
        task=ModelTask.MODEL_READINESS,
        tier=ModelTier.MAX,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        response_format="json",
        temperature=0.0,
        max_tokens=4096,
        metadata={
            "job_id": job_id,
            "module_name": "requirements_review",
        },
    )
    review = _normalize_review(result.parsed_json if not result.error else None)
    if result.error:
        review["physics_risks"].append(f"MAX requirements review failed: {result.error}")
    request = {
        "schema_version": "requirements_review_v1",
        "source": "requirements_review_max",
        "summary_for_user": review["summary_for_user"],
        "missing_information": review["missing_information"],
        "ambiguous_fields": review["ambiguous_parameters"],
        "ambiguous_parameters": review["ambiguous_parameters"],
        "physics_risks": review["physics_risks"],
        "questions": review["questions"],
        "proposed_parameters": review["proposed_parameters"],
        "proposed_defaults": review["proposed_defaults"],
        "task_spec": task_spec,
        "model_error": result.error or "",
    }
    request_path = review_dir / REQUIREMENTS_REVIEW_REQUEST
    request_path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "requirements_review_status": "pending",
        "requirements_review_request_path": str(request_path),
        "confirmation_status": "pending",
        "confirmation_request_path": str(request_path),
        "confirmation_summary": review["summary_for_user"],
        "human_confirmation_required": True,
        "current_node": "requirements_review",
    }


def approve_requirements_review(
    state: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, Any]:
    job_id = str(state.get("job_id") or "unknown")
    review_dir = get_stage_dir(job_id, STAGE_TASK_PLAN)
    review_dir.mkdir(parents=True, exist_ok=True)
    request_path = str(state.get("requirements_review_request_path") or state.get("confirmation_request_path") or "")
    request = _read_json(request_path)
    response_path = review_dir / REQUIREMENTS_REVIEW_RESPONSE
    confirmed_path = review_dir / CONFIRMED_REQUIREMENT_PLAN
    response_doc = {
        "schema_version": "requirements_review_response_v1",
        "request_path": request_path,
        "user_response": response,
    }
    confirmed = {
        "schema_version": "confirmed_requirement_plan_v1",
        "source": "requirements_review",
        "request_path": request_path,
        "response_path": str(response_path),
        "approval_status": "approved",
        "user_response": response,
        "review": request,
        "agent_context": {
            "purpose": "hard_constraints_for_g4_modeling",
            "instruction": (
                "Treat this confirmed requirement plan as the user-approved "
                "source of truth for Geant4 modeling and code generation."
            ),
        },
    }
    response_path.write_text(
        json.dumps(response_doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    confirmed_path.write_text(
        json.dumps(confirmed, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "requirements_review_status": "approved",
        "requirements_review_response_path": str(response_path),
        "confirmed_requirement_plan_path": str(confirmed_path),
        "confirmation_status": "approved",
        "human_confirmation_required": False,
        "raw_human_response": response,
    }


def reject_requirements_review(state: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    job_id = str(state.get("job_id") or "unknown")
    review_dir = get_stage_dir(job_id, STAGE_TASK_PLAN)
    review_dir.mkdir(parents=True, exist_ok=True)
    response_path = review_dir / REQUIREMENTS_REVIEW_RESPONSE
    response_doc = {
        "schema_version": "requirements_review_response_v1",
        "request_path": str(
            state.get("requirements_review_request_path")
            or state.get("confirmation_request_path")
            or ""
        ),
        "user_response": response,
        "approval_status": "rejected",
    }
    response_path.write_text(
        json.dumps(response_doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "requirements_review_status": "rejected",
        "requirements_review_response_path": str(response_path),
        "confirmation_status": "rejected",
        "human_confirmation_required": False,
        "raw_human_response": response,
    }


def _normalize_review(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    return {
        "summary_for_user": str(
            data.get("summary_for_user")
            or "请确认仿真目标、关键参数和继续执行条件。"
        ),
        "missing_information": _string_list(data.get("missing_information")),
        "ambiguous_parameters": _dict_list(
            data.get("ambiguous_parameters") or data.get("ambiguous_fields")
        ),
        "physics_risks": _string_list(data.get("physics_risks")),
        "questions": _dict_list(data.get("questions")),
        "proposed_parameters": _dict_list(data.get("proposed_parameters")),
        "proposed_defaults": _dict_list(data.get("proposed_defaults")),
    }


def _read_json(path: str) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
