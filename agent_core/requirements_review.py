from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_core.models import gateway as model_gateway
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_stage_dir
from agent_core.workspace.paths import STAGE_TASK_PLAN

REQUIREMENTS_REVIEW_REQUEST = "requirements_review_request.json"
REQUIREMENTS_REVIEW_RESPONSE = "requirements_review_response.json"
CONFIRMED_REQUIREMENT_PLAN = "confirmed_requirement_plan.json"


SYSTEM_PROMPT = """You are RadAgent's pre-codegen Geant4 requirements reviewer.

Review the user's simulation request and extracted task_spec before any Geant4
model IR or C++ code is generated. Use fast model judgment to find missing,
ambiguous, risky, or defaulted parameters that a human should see.

Return JSON only with:
{
  "status": "needs_user_input|pass",
  "summary_for_user": "...",
  "missing_information": ["..."],
  "ambiguous_parameters": [{"field_path":"...", "proposed_value":"...", "reason":"..."}],
  "physics_risks": ["..."],
  "questions": [
    {
      "field_path":"...",
      "question":"...",
      "recommended_value":"...",
      "reason":"..."
    }
  ],
  "proposed_parameters": [
    {
      "field_path":"...",
      "proposed_value":...,
      "source_type":"user|model_inferred|default",
      "confidence":0.0,
      "requires_confirmation": true
    }
  ],
  "proposed_defaults": [{"field_path":"...", "proposed_value":..., "reason":"..."}]
}

Hard output rules:
- Return one complete JSON object only.
- Do not wrap the JSON in Markdown fences.
- Do not include prose before or after the JSON.
- Never return an empty response. If uncertain, return a valid
  needs_user_input JSON object with concrete questions and recommended values.
- Use standard JSON double quotes (") only; never use curly quotes.
- Ensure every string is closed, every comma is valid, and the object is parseable by json.loads.
- 所有面向用户显示的文字必须使用简体中文，包括 summary_for_user,
  missing_information, ambiguous_parameters.reason, physics_risks,
  questions[].question, questions[].recommended_value, questions[].reason,
  proposed_defaults[].reason, and any explanation intended for the UI.
- If the request is clear enough to build Geant4 code, return "status": "pass"
  and no questions.
- If anything still needs user alignment, return "status": "needs_user_input".
- Every question must include one concrete recommended_value the UI can show as
  the default answer.
- If the input contains confirmed_requirement_answers, treat every listed
  field_path and selected_value as explicit user-confirmed constraints. Do not
  ask again about the same field_path unless a later supplement directly
  contradicts the confirmed value. Carry those values forward as
  source_type="user_confirmed" proposed parameters when relevant.
- If the task_spec contains confirmed_requirement_plan, treat its
  review.proposed_parameters and confirmed_requirement_answers as the current
  source of truth. Do not re-open already approved source, geometry, material,
  scoring, physics-list, production-cut, or surrogate-component decisions.

Focus on particle type, energy/spectrum, source direction/position, materials,
geometry dimensions, layer order, scoring outputs, physics list, production
cuts, step limits, and units.

Runtime boundary:
- Do not ask the user how many events/particles/histories to run, nor propose
  run.events or /run/beamOn counts. Runtime event count is selected later in
  the workbench run controls, not in pre-modeling requirements review.

RadAgent capability boundaries:
- This pipeline rapidly builds downloadable Geant4 source code and project files.
- Do not promise that the pipeline itself directly produces CSV data, plots, or
  a final scientific report. Users can run/download the generated source code.
- Do not ask the user to choose output CSV/report formatting as a requirement.
- This agent does not execute TCAD, SPICE, Sentaurus, Silvaco, circuit
  simulation, threshold-shift extraction, or electrical IV analysis. If the
  user mentions MOSFET, TCAD, SPICE, threshold shift, or electrical response,
  keep the review focused on the Geant4 part: geometry/material stack,
  radiation source, sensitive volumes, dose and energy-deposition scoring.
- The generated code should still include generic sensitive-volume scoring logic
  for dose, energy deposition, step length, track id, event id, particle type,
  and position where applicable.
"""


JSON_REPAIR_SYSTEM_PROMPT = """You are repairing one malformed JSON response.

Return only the repaired JSON object. Do not add Markdown fences or explanation.
Do not change the user's intended parameter values or wording except where needed
to make valid JSON. Use standard JSON double quotes only.
"""


QUESTION_TOOL_SYSTEM_PROMPT = """You are filling RadAgent's internal requirements-question tool.

The previous requirements review response was malformed or unusable. Do not
ask the user to confirm a JSON/parser/model-format problem. Instead, extract or
reconstruct the actual Geant4 modeling questions the user should answer.

Return JSON only in this tool payload shape:
{
  "status": "needs_user_input|pass",
  "summary_for_user": "中文摘要",
  "missing_information": ["中文缺失项"],
  "physics_risks": ["中文风险或注意事项"],
  "cards": [
    {
      "field_path": "source.particle",
      "question": "中文问题",
      "recommended_value": "中文推荐答案或具体值",
      "note": "中文备注，解释为什么推荐"
    }
  ]
}

Rules:
- 所有面向用户显示的文字必须使用简体中文。
- 每个 cards[] 必须包含 question、recommended_value、note。
- question 必须问仿真参数，不得询问是否忽略 JSON 错误。
- recommended_value 必须是一个可直接采用的具体推荐值。
- 只处理 Geant4：源项、能量/能谱、方向/位置、几何、材料、敏感体积、
  计分、物理列表、production cuts、step limits、单位。
- 不得询问运行事件数、粒子数、histories 或 /run/beamOn 数量；这些由
  workbench 运行面板选择。
- 不要要求 TCAD/SPICE/电路仿真参数。
"""


async def requirements_review_node(state: dict[str, Any]) -> dict[str, Any]:
    job_id = str(state.get("job_id") or "unknown")
    task_spec = _read_json(str(state.get("task_spec_path") or ""))
    review_dir = get_stage_dir(job_id, STAGE_TASK_PLAN)
    review_dir.mkdir(parents=True, exist_ok=True)
    confirmed_answers = _confirmed_answers_from_supplements(
        state.get("requirements_review_supplements", [])
    )

    prompt = json.dumps(
        {
            "user_query": state.get("user_query", ""),
            "task_spec": task_spec,
            "context_report_path": state.get("context_report_path", ""),
            "evidence_map_path": state.get("evidence_map_path", ""),
            "previous_requirements_review": _read_json(
                str(
                    state.get("requirements_review_request_path")
                    or state.get("confirmation_request_path")
                    or ""
                )
            ),
            "requirements_review_supplements": state.get(
                "requirements_review_supplements",
                [],
            ),
            "confirmed_requirement_answers": confirmed_answers,
            "confirmed_answer_instruction": (
                "Treat confirmed_requirement_answers as explicit user decisions. "
                "Do not ask again for those exact field_path values; use "
                "selected_value as user_confirmed input for Geant4 modeling."
            ),
            "review_instruction": (
                "Re-evaluate from scratch using the original request, task_spec, "
                "the prior review, all user supplements, and the confirmed "
                "requirement answers. Return pass only when no further user "
                "alignment is needed for unconfirmed fields."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )
    gateway = model_gateway.get_model_gateway()
    result = await gateway.call(
        task=ModelTask.MODEL_READINESS,
        tier=ModelTier.LITE,
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
    parsed_review, json_repair = await _parsed_review_or_repair(
        gateway=gateway,
        job_id=job_id,
        result=result,
    )
    if parsed_review is None and not result.error:
        parsed_review = _fallback_review_from_malformed_content(
            getattr(result, "content", ""),
            task_spec=task_spec,
            include_defaults=False,
        )
        if parsed_review and parsed_review.get("questions"):
            json_repair["fallback_extracted"] = True
        else:
            parsed_review, question_tool_meta = await _question_tool_review_from_unusable_json(
                gateway=gateway,
                job_id=job_id,
                original_prompt=prompt,
                malformed_content=getattr(result, "content", ""),
                task_spec=task_spec,
                json_repair=json_repair,
            )
            json_repair.update(question_tool_meta)
            if parsed_review is None:
                parsed_review = _fallback_review_from_malformed_content(
                    getattr(result, "content", ""),
                    task_spec=task_spec,
                    include_defaults=True,
                )
                json_repair["fallback_extracted"] = True
    review = _normalize_review(parsed_review if not result.error else None)
    review = _strip_runtime_event_count_review_items(review)
    review = _apply_confirmed_requirement_answers(review, confirmed_answers)
    if result.error:
        review["physics_risks"].append(f"Lite requirements review failed: {result.error}")
    request = {
        "schema_version": "requirements_review_v1",
        "source": "requirements_review_lite",
        "status": review["status"],
        "summary_for_user": review["summary_for_user"],
        "missing_information": review["missing_information"],
        "ambiguous_fields": review["ambiguous_parameters"],
        "ambiguous_parameters": review["ambiguous_parameters"],
        "physics_risks": review["physics_risks"],
        "questions": review["questions"],
        "proposed_parameters": review["proposed_parameters"],
        "proposed_defaults": review["proposed_defaults"],
        "confirmed_requirement_answers": confirmed_answers,
        "task_spec": task_spec,
        "model_error": result.error or "",
        "json_repair": json_repair,
    }
    request_path = review_dir / REQUIREMENTS_REVIEW_REQUEST
    request_path.write_text(json.dumps(request, indent=2, ensure_ascii=False), encoding="utf-8")
    if _review_passed(review):
        approved = approve_requirements_review(
            {
                **state,
                "requirements_review_request_path": str(request_path),
                "confirmation_request_path": str(request_path),
            },
            {
                "user_decision": "model_pass",
                "feedback": "Lite requirements review passed after user alignment.",
                "requirements_review_supplements": state.get(
                    "requirements_review_supplements",
                    [],
                ),
            },
        )
        return {
            **approved,
            "requirements_review_request_path": str(request_path),
            "confirmation_request_path": str(request_path),
            "confirmation_summary": review["summary_for_user"],
            "current_node": "requirements_review",
        }
    return {
        "requirements_review_status": "needs_user_input",
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
    request_path = str(
        state.get("requirements_review_request_path")
        or state.get("confirmation_request_path")
        or ""
    )
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
    status = str(data.get("status") or data.get("review_status") or "").strip().lower()
    if status in {"passed", "approved", "ready", "ok", "complete", "completed"}:
        status = "pass"
    elif status != "pass":
        status = "needs_user_input"
    return {
        "status": status,
        "summary_for_user": str(
            data.get("summary_for_user")
            or "请确认仿真目标、关键参数和继续执行条件。"
        ),
        "missing_information": _string_list(data.get("missing_information")),
        "ambiguous_parameters": _dict_list(
            data.get("ambiguous_parameters") or data.get("ambiguous_fields")
        ),
        "physics_risks": _string_list(data.get("physics_risks")),
        "questions": [_normalize_question(item) for item in _dict_list(data.get("questions"))],
        "proposed_parameters": _dict_list(data.get("proposed_parameters")),
        "proposed_defaults": _dict_list(data.get("proposed_defaults")),
    }


CONFIRMATION_JSON_MARKER = "RADAGENT_CONFIRMATION_JSON:"


def _confirmed_answers_from_supplements(value: Any) -> list[dict[str, Any]]:
    """Extract machine-readable human parameter choices from review supplements.

    Older UI builds only sent text lines such as
    ``source.energy: 确认推荐 150 MeV``. Newer builds append a JSON payload.
    Accept both shapes so existing paused jobs keep working after reload.
    """
    by_field: dict[str, dict[str, Any]] = {}
    for supplement in _dict_list(value):
        feedback = str(
            supplement.get("feedback")
            or supplement.get("user_notes")
            or supplement.get("note")
            or ""
        )
        for answer in _confirmed_answers_from_feedback_text(feedback):
            by_field[answer["field_path"]] = answer
        payload = _confirmation_json_payload_from_text(feedback)
        if payload:
            for item in _dict_list(
                payload.get("confirmed_parameters")
                or payload.get("answers")
                or payload.get("parameters")
            ):
                answer = _normalize_confirmed_answer(item, source="machine_payload")
                if answer:
                    by_field[answer["field_path"]] = answer
    return list(by_field.values())


def _confirmation_json_payload_from_text(text: str) -> dict[str, Any]:
    marker_index = text.find(CONFIRMATION_JSON_MARKER)
    if marker_index < 0:
        return {}
    raw = text[marker_index + len(CONFIRMATION_JSON_MARKER) :].strip()
    if not raw:
        return {}
    try:
        parsed, _ = json.JSONDecoder().raw_decode(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _confirmed_answers_from_feedback_text(text: str) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(CONFIRMATION_JSON_MARKER):
            continue
        match = re.match(r"^([^:\n]{1,180})\s*:\s*(确认推荐|修改为)\s+(.+)$", stripped)
        if not match:
            continue
        field_path = match.group(1).strip()
        if field_path in {"补充说明", "note", "feedback"}:
            continue
        selected_value = match.group(3).strip()
        if not field_path or not selected_value:
            continue
        answers.append(
            {
                "schema_version": "requirements_review_answer_v1",
                "field_path": field_path,
                "decision": "modify" if match.group(2) == "修改为" else "accept_recommended",
                "selected_value": selected_value,
                "recommended_value": selected_value if match.group(2) == "确认推荐" else "",
                "question": "",
                "reason": "",
                "source": "text_supplement",
            }
        )
    return answers


def _normalize_confirmed_answer(item: dict[str, Any], *, source: str) -> dict[str, Any]:
    field_path = str(
        item.get("field_path")
        or item.get("path")
        or item.get("id")
        or ""
    ).strip()
    selected_value = item.get("selected_value")
    if selected_value in (None, ""):
        selected_value = item.get("value")
    if selected_value in (None, ""):
        selected_value = item.get("proposed_value")
    if selected_value in (None, ""):
        selected_value = item.get("recommended_value")
    if not field_path or selected_value in (None, ""):
        return {}
    decision = str(item.get("decision") or "").strip() or "accept_recommended"
    return {
        "schema_version": "requirements_review_answer_v1",
        "field_path": field_path,
        "question": str(item.get("question") or "").strip(),
        "decision": decision,
        "selected_value": selected_value,
        "recommended_value": item.get("recommended_value", ""),
        "reason": str(item.get("reason") or item.get("note") or "").strip(),
        "source": source,
    }


def _apply_confirmed_requirement_answers(
    review: dict[str, Any],
    confirmed_answers: list[dict[str, Any]],
) -> dict[str, Any]:
    if not confirmed_answers:
        return review
    confirmed_by_field = {
        str(answer.get("field_path") or "").strip(): answer
        for answer in confirmed_answers
        if str(answer.get("field_path") or "").strip()
    }
    if not confirmed_by_field:
        return review
    result = dict(review)
    result["missing_information"] = [
        item
        for item in _string_list(result.get("missing_information"))
        if not _missing_info_matches_confirmed_answer(item, confirmed_by_field.values())
    ]
    result["questions"] = [
        item
        for item in _dict_list(result.get("questions"))
        if _review_item_field_path(item) not in confirmed_by_field
    ]
    result["ambiguous_parameters"] = [
        item
        for item in _dict_list(result.get("ambiguous_parameters"))
        if _review_item_field_path(item) not in confirmed_by_field
    ]
    result["proposed_defaults"] = [
        item
        for item in _dict_list(result.get("proposed_defaults"))
        if _review_item_field_path(item) not in confirmed_by_field
    ]
    existing_parameters = [
        item
        for item in _dict_list(result.get("proposed_parameters"))
        if _review_item_field_path(item) not in confirmed_by_field
    ]
    confirmed_parameters = [
        _confirmed_answer_as_proposed_parameter(answer)
        for answer in confirmed_by_field.values()
    ]
    result["proposed_parameters"] = [*confirmed_parameters, *existing_parameters]
    result["confirmed_requirement_answers"] = list(confirmed_by_field.values())
    if (
        result.get("status") != "pass"
        and not result.get("missing_information")
        and not result.get("ambiguous_parameters")
        and not result.get("questions")
    ):
        result["status"] = "pass"
        result["summary_for_user"] = (
            str(result.get("summary_for_user") or "").strip()
            or "已记录用户确认的推荐参数，可以进入 Geant4 建模。"
        )
    return result


def _missing_info_matches_confirmed_answer(
    missing_information: str,
    confirmed_answers: Any,
) -> bool:
    missing_key = _normalized_review_text(missing_information)
    if not missing_key:
        return False
    for answer in confirmed_answers:
        for marker in _confirmed_answer_markers(answer):
            if marker and (marker in missing_key or missing_key in marker):
                return True
    return False


def _confirmed_answer_markers(answer: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    for key in ("field_path", "selected_value", "recommended_value", "question"):
        raw = str(answer.get(key) or "")
        normalized = _normalized_review_text(raw)
        if len(normalized) >= 6:
            markers.append(normalized)
    question = str(answer.get("question") or "")
    for fragment in re.split(r"是否|请确认|还是|或者|或|和|以及|、|，|。|；|：|:|\?|？", question):
        cleaned = _normalized_review_text(fragment)
        cleaned = re.sub(r"^(坚持|保持|采用|使用|改为|设置为)", "", cleaned)
        if len(cleaned) >= 4:
            markers.append(cleaned)
    selected = str(answer.get("selected_value") or answer.get("recommended_value") or "")
    for fragment in re.split(r"、|，|。|；|：|:|\s+", selected):
        cleaned = _normalized_review_text(fragment)
        cleaned = re.sub(r"^(坚持|保持|采用|使用|改为|设置为)", "", cleaned)
        if len(cleaned) >= 4:
            markers.append(cleaned)
    return list(dict.fromkeys(markers))


def _normalized_review_text(value: Any) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").lower())


def _review_item_field_path(item: dict[str, Any]) -> str:
    return str(
        item.get("field_path")
        or item.get("path")
        or item.get("parameter")
        or item.get("id")
        or ""
    ).strip()


def _confirmed_answer_as_proposed_parameter(answer: dict[str, Any]) -> dict[str, Any]:
    return {
        "field_path": str(answer.get("field_path") or "").strip(),
        "proposed_value": answer.get("selected_value"),
        "source_type": "user_confirmed",
        "confidence": 1.0,
        "requires_confirmation": False,
        "reason": str(
            answer.get("reason")
            or answer.get("question")
            or "Confirmed by the user during requirements review."
        ).strip(),
    }


def _fallback_review_from_malformed_content(
    content: Any,
    *,
    task_spec: dict[str, Any],
    include_defaults: bool = True,
) -> dict[str, Any]:
    """Extract usable review cards from a malformed MAX JSON response.

    The MAX response can be semantically good but syntactically broken, often
    because one Chinese quote or an unfinished tail invalidates the whole JSON.
    This fallback is deliberately conservative: recover top-level lists and
    question objects when possible, then add deterministic questions from the
    task spec so the UI never shows an empty confirmation gate.
    """
    text = str(content or "")
    review: dict[str, Any] = {
        "status": "needs_user_input",
        "summary_for_user": _extract_json_string_field(text, "summary_for_user")
        or "请确认仿真目标、关键参数和继续执行条件。",
        "missing_information": _extract_string_array_field(text, "missing_information"),
        "ambiguous_parameters": _extract_object_array_field(text, "ambiguous_parameters"),
        "physics_risks": _extract_string_array_field(text, "physics_risks"),
        "questions": _extract_object_array_field(text, "questions"),
        "proposed_parameters": [],
        "proposed_defaults": [],
    }
    if include_defaults and not review["questions"]:
        review["questions"] = _default_questions_from_task_spec(task_spec, review)
    return review


def _extract_json_string_field(content: str, field: str) -> str:
    pattern = rf'"{re.escape(field)}"\s*:\s*"((?:\\.|[^"\\])*)'
    match = re.search(pattern, content, flags=re.DOTALL)
    if not match:
        return ""
    return _decode_json_string_fragment(match.group(1))


def _decode_json_string_fragment(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value.replace('\\"', '"').strip()


def _extract_string_array_field(content: str, field: str) -> list[str]:
    body = _extract_array_body(content, field)
    if not body:
        return []
    values: list[str] = []
    for match in re.finditer(r'"((?:\\.|[^"\\])*)"', body, flags=re.DOTALL):
        text = _decode_json_string_fragment(match.group(1)).strip()
        if text:
            values.append(text)
    return values


def _extract_object_array_field(content: str, field: str) -> list[dict[str, Any]]:
    body = _extract_array_body(content, field)
    if not body:
        return []
    objects: list[dict[str, Any]] = []
    for raw in _iter_json_object_fragments(body):
        parsed = _parse_loose_json_object(raw)
        if parsed:
            objects.append(parsed)
    return objects


def _extract_array_body(content: str, field: str) -> str:
    marker = re.search(rf'"{re.escape(field)}"\s*:\s*\[', content)
    if not marker:
        return ""
    start = marker.end() - 1
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(content)):
        char = content[idx]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return content[start + 1 : idx]
    return content[start + 1 :]


def _iter_json_object_fragments(content: str) -> list[str]:
    objects: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escape = False
    for idx, char in enumerate(content):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                objects.append(content[start : idx + 1])
                start = None
    return objects


def _parse_loose_json_object(raw: str) -> dict[str, Any]:
    normalized = raw.replace("“", '"').replace("”", '"')
    normalized = re.sub(r",\s*}", "}", normalized)
    try:
        data = json.loads(normalized)
    except json.JSONDecodeError:
        data = {
            key: _decode_json_string_fragment(value)
            for key, value in re.findall(
                r'"([^"\\]+)"\s*:\s*"((?:\\.|[^"\\])*)"',
                normalized,
                flags=re.DOTALL,
            )
        }
    return data if isinstance(data, dict) else {}


def _default_questions_from_task_spec(
    task_spec: dict[str, Any],
    review: dict[str, Any],
) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    hinted_questions = _hinted_questions_from_task_spec(task_spec)
    if hinted_questions:
        return hinted_questions

    particle = task_spec.get("particle") if isinstance(task_spec.get("particle"), dict) else {}
    particle_type = str(particle.get("type") or "").strip()
    energy = particle.get("energy_MeV")
    energy_unit = str(particle.get("energy_unit") or "MeV")
    if particle_type:
        questions.append(
            {
                "field_path": "source.particle_energy",
                "question": "请确认辐照粒子和能量是否按当前设置继续？",
                "recommended_value": f"{particle_type} {energy} {energy_unit}".strip(),
                "reason": "这是后续 Geant4 源项和物理列表选择的核心输入。",
            }
        )

    missing_text = "；".join(str(item) for item in review.get("missing_information", []))
    if "厚" in missing_text or "layer" in missing_text.lower() or "屏蔽" in missing_text:
        questions.append(
            {
                "field_path": "geometry.layer_thicknesses",
                "question": "请确认各屏蔽层或关键几何层的厚度。",
                "recommended_value": "按用户材料顺序使用典型初值：聚乙烯 5 cm，含硼聚乙烯 5 cm，铅 2 cm，硅探测器 3 mm",
                "reason": "任务规划缺少几何厚度，无法可靠构建屏蔽体。",
            }
        )
    if "顺序" in missing_text or "stack" in missing_text.lower():
        questions.append(
            {
                "field_path": "geometry.stack_order",
                "question": "请确认从源到探测器的材料排列顺序。",
                "recommended_value": "源 -> 聚乙烯 -> 含硼聚乙烯 -> 铅 -> 硅探测器",
                "reason": "材料顺序会显著影响中子慢化、俘获和次级伽马产生。",
            }
        )
    if questions:
        return questions
    return [
        {
            "field_path": "source.definition",
            "question": "请确认辐照源的粒子类型、能量或能谱、入射方向和源形状。",
            "recommended_value": "gamma，1 MeV 单能，沿 +Z 方向垂直入射，平行束",
            "reason": "Geant4 工程必须有明确源项才能选择物理列表并生成 PrimaryGeneratorAction。",
        },
        {
            "field_path": "geometry.material_stack",
            "question": "请确认要建模的几何结构、材料栈和关键尺寸。",
            "recommended_value": "使用简化可运行几何：空气世界，硅衬底，SiO2 栅氧化层，金属栅；尺寸按常规 MOSFET 辐照基准设置",
            "reason": "缺少几何和材料时无法定义 DetectorConstruction 和敏感体积。",
        },
        {
            "field_path": "scoring.sensitive_volume",
            "question": "请确认剂量和能量沉积的敏感体积。",
            "recommended_value": "栅氧化层",
            "reason": "MOSFET Geant4 阶段应聚焦敏感体积内的能量沉积、剂量、步长、粒子类型和位置记录。",
        },
    ]


def _hinted_questions_from_task_spec(task_spec: dict[str, Any]) -> list[dict[str, Any]]:
    hints = task_spec.get("requirements_review_hints")
    questions = _dict_list(hints.get("questions") if isinstance(hints, dict) else None)
    normalized = [_normalize_question_tool_card(item, index) for index, item in enumerate(questions)]
    normalized = [item for item in normalized if item]
    if normalized:
        return normalized

    clarification = task_spec.get("clarification_request")
    clarification_questions = _dict_list(
        clarification.get("questions") if isinstance(clarification, dict) else None
    )
    result: list[dict[str, Any]] = []
    for index, item in enumerate(clarification_questions):
        card = _normalize_question_tool_card(
            {
                **item,
                "recommended_value": item.get("recommended_value")
                or _recommended_value_for_clarification(item),
                "reason": item.get("reason")
                or "该参数会决定 Geant4 几何、源项或敏感体积的实现。",
            },
            index,
        )
        if card:
            result.append(card)
    return result


def _recommended_value_for_clarification(item: dict[str, Any]) -> str:
    key = str(item.get("id") or item.get("field_path") or "").lower()
    if "sensitive" in key or "volume" in key or "敏感" in key:
        return "栅氧化层"
    if "source" in key or "particle" in key or "源" in key:
        return "gamma，1 MeV 单能，沿 +Z 方向垂直入射，平行束"
    if "geometry" in key or "device" in key or "结构" in key:
        return "简化 MOSFET：硅衬底、SiO2 栅氧化层、金属栅，空气世界包围"
    return "采用推荐默认值继续"


async def _question_tool_review_from_unusable_json(
    *,
    gateway: Any,
    job_id: str,
    original_prompt: str,
    malformed_content: Any,
    task_spec: dict[str, Any],
    json_repair: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    result = await gateway.call(
        task=ModelTask.MODEL_READINESS,
        tier=ModelTier.LITE,
        system_prompt=QUESTION_TOOL_SYSTEM_PROMPT,
        user_prompt=json.dumps(
            {
                "instruction": (
                    "The requirements review JSON and repair attempt were unusable. "
                    "Fill the internal question-card tool. Do not surface parser "
                    "or JSON errors to the user."
                ),
                "original_requirements_review_prompt": original_prompt,
                "task_spec": task_spec,
                "malformed_review_content": str(malformed_content or ""),
                "json_repair": json_repair,
            },
            ensure_ascii=False,
            indent=2,
        ),
        response_format="json",
        temperature=0.0,
        max_tokens=2048,
        metadata={
            "job_id": job_id,
            "module_name": "requirements_review_question_tool",
        },
    )
    meta = {
        "question_tool_attempted": True,
        "question_tool_used": False,
        "question_tool_error": str(result.error or ""),
        "question_tool_content_preview": _preview_text(getattr(result, "content", "")),
    }
    if result.error:
        return None, meta
    review = _review_from_question_tool_payload(result.parsed_json)
    if review is None:
        meta["question_tool_error"] = "Question tool returned no usable cards."
        return None, meta
    meta["question_tool_used"] = True
    return review, meta


def _review_from_question_tool_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    raw_cards = (
        value.get("cards")
        or value.get("questions")
        or value.get("question_cards")
        or value.get("items")
    )
    cards = [
        _normalize_question_tool_card(item, index)
        for index, item in enumerate(_dict_list(raw_cards))
    ]
    questions = [item for item in cards if item]
    if not questions and str(value.get("status") or "").strip().lower() != "pass":
        return None
    status = str(value.get("status") or "").strip().lower()
    if status not in {"pass", "needs_user_input"}:
        status = "needs_user_input" if questions else "pass"
    return {
        "status": status,
        "summary_for_user": str(
            value.get("summary_for_user")
            or "请确认 Geant4 建模参数后继续。"
        ),
        "missing_information": _string_list(value.get("missing_information")),
        "ambiguous_parameters": [],
        "physics_risks": _string_list(value.get("physics_risks")),
        "questions": questions,
        "proposed_parameters": [],
        "proposed_defaults": [],
    }


def _normalize_question_tool_card(item: dict[str, Any], index: int) -> dict[str, Any]:
    field_path = str(item.get("field_path") or item.get("path") or "").strip()
    if not field_path:
        field_path = f"requirements.question_{index + 1}"
    question = str(item.get("question") or item.get("title") or "").strip()
    recommended = item.get("recommended_value")
    if recommended in (None, ""):
        recommended = item.get("proposed_value") or item.get("default_value")
    recommended_text = str(recommended or "").strip()
    reason = str(
        item.get("reason")
        or item.get("note")
        or item.get("备注")
        or item.get("rationale")
        or item.get("detail")
        or ""
    ).strip()
    if not question or not recommended_text:
        return {}
    return {
        "field_path": field_path,
        "question": question,
        "recommended_value": recommended_text,
        "reason": reason,
    }


def _strip_runtime_event_count_review_items(review: dict[str, Any]) -> dict[str, Any]:
    result = dict(review)
    result["missing_information"] = [
        item
        for item in _string_list(result.get("missing_information"))
        if not _is_runtime_event_count_text(item)
    ]
    result["ambiguous_parameters"] = [
        item
        for item in _dict_list(result.get("ambiguous_parameters"))
        if not _is_runtime_event_count_item(item)
    ]
    result["questions"] = [
        item
        for item in _dict_list(result.get("questions"))
        if not _is_runtime_event_count_item(item)
    ]
    result["proposed_parameters"] = [
        item
        for item in _dict_list(result.get("proposed_parameters"))
        if not _is_runtime_event_count_item(item)
    ]
    result["proposed_defaults"] = [
        item
        for item in _dict_list(result.get("proposed_defaults"))
        if not _is_runtime_event_count_item(item)
    ]
    return result


def _is_runtime_event_count_item(item: dict[str, Any]) -> bool:
    field_path = str(item.get("field_path") or item.get("path") or "").strip().lower()
    if field_path in {
        "run.events",
        "runtime.events",
        "simulation.events",
        "source.events",
        "events",
    }:
        return True
    if field_path.endswith(".events") or field_path.endswith(".event_count"):
        return True
    return _is_runtime_event_count_text(
        " ".join(
            str(item.get(key) or "")
            for key in (
                "question",
                "recommended_value",
                "proposed_value",
                "default_value",
                "reason",
                "note",
            )
        )
    )


def _is_runtime_event_count_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    runtime_markers = (
        "run.events",
        "/run/beamon",
        "beam on",
        "beamon",
        "event count",
        "number of events",
        "how many events",
        "histories",
        "事件数",
        "粒子事件",
        "多少个粒子",
        "多少事件",
        "运行多少",
        "模拟多少",
    )
    return any(marker in text for marker in runtime_markers)


def _review_passed(review: dict[str, Any]) -> bool:
    return (
        review.get("status") == "pass"
        and not review.get("missing_information")
        and not review.get("ambiguous_parameters")
        and not review.get("questions")
    )


def _normalize_question(item: dict[str, Any]) -> dict[str, Any]:
    question = dict(item)
    recommended = (
        question.get("recommended_value")
        if question.get("recommended_value") not in (None, "")
        else question.get("proposed_value")
    )
    if recommended in (None, ""):
        recommended = question.get("default_value", "")
    question["recommended_value"] = recommended
    if "proposed_value" not in question and recommended not in (None, ""):
        question["proposed_value"] = recommended
    return question


async def _parsed_review_or_repair(
    *,
    gateway: Any,
    job_id: str,
    result: Any,
) -> tuple[Any | None, dict[str, Any]]:
    if result.parsed_json is not None or result.error:
        return result.parsed_json, {
            "attempted": False,
            "repaired": False,
            "initial_error": "",
            "repair_error": "",
            "raw_content_preview": _preview_text(getattr(result, "content", "")),
        }
    initial_error = _json_parse_error(getattr(result, "content", ""))
    repair_result = await gateway.call(
        task=ModelTask.MODEL_READINESS,
        tier=ModelTier.LITE,
        system_prompt=JSON_REPAIR_SYSTEM_PROMPT,
        user_prompt=json.dumps(
            {
                "instruction": (
                    "JSON parse failed. Repair the malformed requirements review "
                    "response into one valid JSON object matching the original schema."
                ),
                "parse_error": initial_error,
                "malformed_content": getattr(result, "content", ""),
            },
            ensure_ascii=False,
            indent=2,
        ),
        response_format="json",
        temperature=0.0,
        max_tokens=4096,
        metadata={
            "job_id": job_id,
            "module_name": "requirements_review_json_repair",
        },
    )
    repair_error = str(repair_result.error or "")
    if repair_result.parsed_json is None and not repair_error:
        repair_error = _json_parse_error(getattr(repair_result, "content", ""))
    parsed_json = repair_result.parsed_json
    repaired = _looks_like_requirements_review(parsed_json)
    if parsed_json is not None and not repaired and not repair_error:
        repair_error = "JSON repair returned parseable JSON that does not match requirements_review_v1."
    return parsed_json if repaired else None, {
        "attempted": True,
        "repaired": repaired,
        "initial_error": initial_error,
        "repair_error": repair_error,
        "raw_content_preview": _preview_text(getattr(result, "content", "")),
        "repair_content_preview": _preview_text(getattr(repair_result, "content", "")),
    }


def _looks_like_requirements_review(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    review_keys = {
        "status",
        "review_status",
        "summary_for_user",
        "missing_information",
        "ambiguous_parameters",
        "ambiguous_fields",
        "physics_risks",
        "questions",
        "proposed_parameters",
        "proposed_defaults",
    }
    if not any(key in value for key in review_keys):
        return False
    if value.get("status") == "pass" or value.get("review_status") == "pass":
        return True
    return any(
        bool(value.get(key))
        for key in (
            "summary_for_user",
            "missing_information",
            "ambiguous_parameters",
            "ambiguous_fields",
            "physics_risks",
            "questions",
            "proposed_parameters",
            "proposed_defaults",
        )
    )


def _json_parse_error(content: str) -> str:
    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        return f"JSON parse failed at line {exc.lineno}, column {exc.colno}: {exc.msg}"
    except TypeError as exc:
        return f"JSON parse failed: {exc}"
    return "JSON parse failed: gateway returned parsed_json=None for JSON response."


def _preview_text(value: Any, limit: int = 2000) -> str:
    text = str(value or "")
    return text[:limit]


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
