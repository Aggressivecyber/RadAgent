"""Human confirmation nodes for RadAgent.

These nodes implement the human-in-the-loop confirmation process
for AI-proposed model completions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from agent_core.human_confirmation.prompts import (
    CONFIRMATION_ROUND_LIMIT,
    MAX_QUESTIONS_PER_ROUND,
    QUESTION_PRIORITY,
    build_confirmation_summary,
)
from agent_core.human_confirmation.reports import generate_confirmation_report
from agent_core.human_confirmation.schemas import (
    ConfirmationRecord,
    ConfirmationRequest,
    ConfirmationResponse,
    ProposedModelCompletion,
)
from agent_core.human_confirmation.validators import validate_human_confirmation
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import STAGE_HUMAN_CONFIRMATION


class HumanConfirmationState(TypedDict, total=False):
    """State for human confirmation subgraph."""

    job_id: str
    user_query: str
    g4_model_ir_path: str
    evidence_map_path: str
    confirmation_status: str
    confirmation_request_path: str
    confirmation_response_path: str
    confirmation_record_path: str
    confirmed_model_plan_path: str
    unconfirmed_assumptions_count: int
    human_confirmation_required: bool
    human_confirmation_round: int
    raw_human_response: dict[str, Any]
    errors: list[str]


def _get_confirmation_dir(job_id: str) -> Path:
    """Return the confirmation directory for a job.

    Creates the directory if it doesn't exist.
    """
    conf_dir = get_job_dir(job_id) / STAGE_HUMAN_CONFIRMATION
    conf_dir.mkdir(parents=True, exist_ok=True)
    return conf_dir


def _load_json(path: Path) -> dict[str, Any] | None:
    """Load JSON file if it exists, return None otherwise."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def _save_json(data: dict[str, Any], path: Path) -> None:
    """Save data to JSON file with proper formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


async def build_proposed_model_completion(
    state: HumanConfirmationState,
) -> dict[str, Any]:
    """Build proposed model completion from model IR and evidence.

    Analyzes the model IR and evidence map to identify:
    - User-provided parameters (confidence=1.0, no confirmation needed)
    - RAG/Web-completed parameters (confidence 0.7-0.9, confirmation needed)
    - Assumptions (confidence 0.3-0.5, confirmation needed)

    Returns dict with proposed_model_completion_path.
    """
    errors: list[str] = []
    job_id = state["job_id"]
    user_query = state.get("user_query", "")
    g4_model_ir_path = state.get("g4_model_ir_path", "")
    evidence_map_path = state.get("evidence_map_path", "")

    # Load model IR
    model_ir: dict[str, Any] = {}
    if g4_model_ir_path:
        ir_path = Path(g4_model_ir_path)
        loaded = _load_json(ir_path)
        if loaded:
            model_ir = loaded
        else:
            errors.append(f"Model IR not found at {g4_model_ir_path}")

    # Load evidence map
    evidence_map: dict[str, Any] = {}
    if evidence_map_path:
        ev_path = Path(evidence_map_path)
        loaded = _load_json(ev_path)
        if loaded:
            evidence_map = loaded

    # Build proposed completion
    proposed: dict[str, Any] = {
        "schema_version": "proposed_model_completion_v1",
        "job_id": job_id,
        "source_query": user_query,
        "domain_profile": "geant4",
        "proposed_components": [],
        "proposed_sources": [],
        "proposed_scoring": [],
        "missing_information": [],
        "assumptions": [],
        "requires_human_confirmation": False,
        "readiness_status": "draft",
        "readiness_score": 0.0,
    }

    # Track which fields were user-provided vs AI-completed
    user_fields: set[str] = set()
    ai_fields: dict[str, dict[str, Any]] = {}  # field -> {source, confidence}

    # Process components
    components = model_ir.get("components", [])
    for comp in components:
        cid = comp.get("component_id", "")
        comp_data: dict[str, Any] = {
            "component_id": cid,
            "component_type": comp.get("component_type", ""),
            "material_id": comp.get("material_id"),
            "geometry": comp.get("geometry", {}),
            "placement": comp.get("placement", {}),
            "roles": comp.get("roles", []),
            "parameters": [],
            "assumptions": [],
            "confidence": 1.0,
            "requires_confirmation": False,
        }

        # Check each component parameter
        for key, value in comp.items():
            if key in {"component_id", "component_type", "geometry", "placement", "roles"}:
                continue

            field_path = f"components.{cid}.{key}"
            source_type = _get_field_source(field_path, evidence_map)
            confidence = _get_field_confidence(source_type)
            requires_conf = confidence < 1.0

            param: dict[str, Any] = {
                "field_path": field_path,
                "proposed_value": value,
                "source_type": source_type,
                "confidence": confidence,
                "reason": _get_field_reason(field_path, evidence_map),
                "requires_confirmation": requires_conf,
            }

            comp_data["parameters"].append(param)

            if requires_conf:
                comp_data["requires_confirmation"] = True
                comp_data["confidence"] = min(comp_data["confidence"], confidence)
                ai_fields[field_path] = {"source": source_type, "confidence": confidence}
            else:
                user_fields.add(field_path)

        proposed["proposed_components"].append(comp_data)

    # Process sources
    sources = model_ir.get("sources", [])
    for src in sources:
        sid = src.get("source_id", "primary")
        for key, value in src.items():
            if key == "source_id":
                continue

            field_path = f"sources.{sid}.{key}"
            source_type = _get_field_source(field_path, evidence_map)
            confidence = _get_field_confidence(source_type)
            requires_conf = confidence < 1.0

            param: dict[str, Any] = {
                "field_path": field_path,
                "proposed_value": value,
                "source_type": source_type,
                "confidence": confidence,
                "reason": _get_field_reason(field_path, evidence_map),
                "requires_confirmation": requires_conf,
            }

            proposed["proposed_sources"].append(param)

            if requires_conf:
                ai_fields[field_path] = {"source": source_type, "confidence": confidence}

    # Process scoring
    scoring = model_ir.get("scoring", [])
    for sc in scoring:
        sid = sc.get("scoring_id", "dose")
        for key, value in sc.items():
            if key == "scoring_id":
                continue

            field_path = f"scoring.{sid}.{key}"
            source_type = _get_field_source(field_path, evidence_map)
            confidence = _get_field_confidence(source_type)
            requires_conf = confidence < 1.0

            param: dict[str, Any] = {
                "field_path": field_path,
                "proposed_value": value,
                "source_type": source_type,
                "confidence": confidence,
                "reason": _get_field_reason(field_path, evidence_map),
                "requires_confirmation": requires_conf,
            }

            proposed["proposed_scoring"].append(param)

            if requires_conf:
                ai_fields[field_path] = {"source": source_type, "confidence": confidence}

    # Collect assumptions from evidence map
    assumptions = evidence_map.get("assumptions", [])
    if isinstance(assumptions, list):
        proposed["assumptions"] = assumptions

    # Collect missing information
    missing = evidence_map.get("missing_information", [])
    if isinstance(missing, list):
        proposed["missing_information"] = missing

    # Calculate overall readiness
    proposed["requires_human_confirmation"] = len(ai_fields) > 0
    proposed["readiness_score"] = _calculate_readiness_score(user_fields, ai_fields, assumptions)

    # Save to file
    conf_dir = _get_confirmation_dir(job_id)
    output_path = conf_dir / "proposed_model_completion.json"
    proposed = ProposedModelCompletion.model_validate(proposed).model_dump(mode="json")
    _save_json(proposed, output_path)

    return {
        "proposed_model_completion_path": str(output_path),
        "requires_human_confirmation": proposed["requires_human_confirmation"],
        "readiness_score": proposed["readiness_score"],
        "errors": errors,
    }


def _get_field_source(field_path: str, evidence_map: dict[str, Any]) -> str:
    """Determine the source type of a field."""
    user_provided = evidence_map.get("user_provided_fields", [])
    if isinstance(user_provided, list) and field_path in user_provided:
        return "user"

    rag_sources = evidence_map.get("rag_completed_fields", {})
    if field_path in rag_sources:
        return "rag"

    web_sources = evidence_map.get("web_completed_fields", {})
    if field_path in web_sources:
        return "web"

    defaults = evidence_map.get("default_fields", [])
    if isinstance(defaults, list) and field_path in defaults:
        return "default"

    return "assumption"


def _get_field_confidence(source_type: str) -> float:
    """Get confidence score based on source type."""
    confidence_map = {
        "user": 1.0,
        "rag": 0.8,
        "web": 0.7,
        "default": 0.6,
        "assumption": 0.4,
    }
    return confidence_map.get(source_type, 0.4)


def _get_field_reason(field_path: str, evidence_map: dict[str, Any]) -> str:
    """Get the reason/explanation for a field's value."""
    rag_sources = evidence_map.get("rag_completed_fields", {})
    if field_path in rag_sources and isinstance(rag_sources[field_path], dict):
        return rag_sources[field_path].get("reason", "")

    web_sources = evidence_map.get("web_completed_fields", {})
    if field_path in web_sources and isinstance(web_sources[field_path], dict):
        return web_sources[field_path].get("reason", "")

    assumptions = evidence_map.get("assumptions_by_field", {})
    if field_path in assumptions:
        return f"Assumption: {assumptions[field_path]}"

    return ""


def _calculate_readiness_score(
    user_fields: set[str],
    ai_fields: dict[str, dict[str, Any]],
    assumptions: list[str],
) -> float:
    """Calculate overall readiness score (0-1)."""
    total_fields = len(user_fields) + len(ai_fields)
    if total_fields == 0:
        return 0.0

    # Base score from user-provided fields
    user_score = len(user_fields) / total_fields

    # Penalty for low-confidence assumptions
    assumption_penalty = len(assumptions) * 0.05

    # Penalty for low-confidence AI fields
    low_conf_penalty = sum(
        1.0 - f["confidence"] for f in ai_fields.values() if f["confidence"] < 0.7
    ) / max(total_fields, 1)

    score = user_score - assumption_penalty - low_conf_penalty
    return max(0.0, min(1.0, score))


async def generate_confirmation_request(
    state: HumanConfirmationState,
) -> dict[str, Any]:
    """Generate a confirmation request with prioritized questions.

    Collects all parameters requiring confirmation and groups them
    into a round of questions (max MAX_QUESTIONS_PER_ROUND per round).

    Returns dict with confirmation_request_path and round number.
    """
    errors: list[str] = []
    job_id = state["job_id"]
    round_n = state.get("human_confirmation_round", 1)

    # Load proposed model completion
    conf_dir = _get_confirmation_dir(job_id)
    proposal_path = conf_dir / "proposed_model_completion.json"
    proposal = _load_json(proposal_path)

    if not proposal:
        errors.append(f"Proposed model completion not found at {proposal_path}")
        return {"errors": errors, "confirmation_request_path": ""}

    # Collect all fields requiring confirmation
    questions: list[dict[str, Any]] = []

    # Questions from components
    for comp in proposal.get("proposed_components", []):
        for param in comp.get("parameters", []):
            if param.get("requires_confirmation", False):
                questions.append(
                    {
                        "question_id": f"q_{len(questions) + 1}",
                        "field_path": param["field_path"],
                        "question": _build_question_text(param, comp),
                        "proposed_value": param.get("proposed_value"),
                        "unit": param.get("unit"),
                        "options": [],
                        "required": True,
                        "reason": param.get("reason", ""),
                    }
                )

    # Questions from sources
    for src in proposal.get("proposed_sources", []):
        if src.get("requires_confirmation", False):
            questions.append(
                {
                    "question_id": f"q_{len(questions) + 1}",
                    "field_path": src["field_path"],
                    "question": _build_question_text(src, None),
                    "proposed_value": src.get("proposed_value"),
                    "unit": src.get("unit"),
                    "options": [],
                    "required": True,
                    "reason": src.get("reason", ""),
                }
            )

    # Questions from scoring
    for sc in proposal.get("proposed_scoring", []):
        if sc.get("requires_confirmation", False):
            questions.append(
                {
                    "question_id": f"q_{len(questions) + 1}",
                    "field_path": sc["field_path"],
                    "question": _build_question_text(sc, None),
                    "proposed_value": sc.get("proposed_value"),
                    "unit": sc.get("unit"),
                    "options": [],
                    "required": True,
                    "reason": sc.get("reason", ""),
                }
            )

    # Sort by priority
    questions = _sort_questions_by_priority(questions)

    # Limit per round
    questions = questions[:MAX_QUESTIONS_PER_ROUND]

    # Build user-friendly summary
    summary = build_confirmation_summary(
        proposal.get("proposed_components", []),
        proposal.get("proposed_sources", []),
        proposal.get("proposed_scoring", []),
        proposal.get("assumptions", []),
        proposal.get("missing_information", []),
    )

    # Create confirmation request
    request: dict[str, Any] = {
        "schema_version": "confirmation_request_v1",
        "job_id": job_id,
        "round_id": round_n,
        "summary_for_user": summary,
        "proposed_model_completion_path": str(proposal_path),
        "questions": questions,
        "approval_options": ["approve", "edit", "reject", "ask_more"],
    }

    # Save to file
    output_path = conf_dir / f"confirmation_request_round_{round_n}.json"
    request = ConfirmationRequest.model_validate(request).model_dump(mode="json")
    _save_json(request, output_path)

    return {
        "confirmation_request_path": str(output_path),
        "human_confirmation_round": round_n,
        "total_questions": len(questions),
        "errors": errors,
    }


def _build_question_text(param: dict[str, Any], parent: dict[str, Any] | None) -> str:
    """Build a human-readable question for a parameter."""
    field_path = param["field_path"]
    value = param.get("proposed_value", "")
    unit = param.get("unit", "")
    reason = param.get("reason", "")

    # Extract meaningful name from field path
    parts = field_path.split(".")
    field_name = parts[-1] if parts else field_path

    # Build question
    question = f"请确认 {field_name}"

    if parent:
        parent_id = parent.get("component_id", parent.get("source_id", ""))
        if parent_id:
            question = f"请确认 {parent_id} 的 {field_name}"

    if value is not None:
        question += f"（提议值：{value}{f' {unit}' if unit else ''}）"

    if reason:
        question += f"\n理由：{reason}"

    return question


def _sort_questions_by_priority(
    questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort questions by priority using QUESTION_PRIORITY."""

    def get_priority_score(q: dict[str, Any]) -> int:
        field_path = q.get("field_path", "").lower()

        for i, category in enumerate(QUESTION_PRIORITY):
            if category in field_path:
                # Reverse index: higher priority = lower index = higher score
                return len(QUESTION_PRIORITY) - i

        return 0  # Lowest priority

    return sorted(questions, key=get_priority_score, reverse=True)


async def human_interrupt_node(state: HumanConfirmationState) -> dict[str, Any]:
    """Interrupt execution for human input.

    In production, this uses LangGraph interrupt().
    Without raw_human_response, returns pending status — NEVER auto-approves.

    Returns dict with confirmation_status and optional interrupt_payload.
    """
    errors: list[str] = []

    # Check if state already has human response (explicit user input)
    if "raw_human_response" in state and state["raw_human_response"]:
        return {
            "raw_human_response": state["raw_human_response"],
            "confirmation_status": "received",
        }

    # No user response available — return pending, NOT auto-approve
    request_path = state.get("confirmation_request_path", "")
    request = None
    if request_path:
        request = _load_json(Path(request_path))

    return {
        "confirmation_status": "pending",
        "human_confirmation_required": True,
        "confirmation_request_path": request_path,
        "errors": errors,
        "interrupt_payload": {
            "type": "human_confirmation_required",
            "confirmation_request": request,
        },
    }


async def parse_confirmation_response(
    state: HumanConfirmationState,
) -> dict[str, Any]:
    """Parse raw human response into structured ConfirmationResponse.

    Extracts the user's decision and any edits from the raw response.

    Returns dict with confirmation_response_path and user_decision.
    """
    errors: list[str] = []
    job_id = state["job_id"]
    round_n = state.get("human_confirmation_round", 1)

    # Get raw human response
    raw_response = state.get("raw_human_response", {})
    if not raw_response:
        errors.append("No raw human response found in state")
        return {"errors": errors, "user_decision": "reject"}

    # Extract decision
    user_decision = raw_response.get("user_decision", "approve")

    # Validate decision
    valid_decisions = {"approve", "edit", "reject", "ask_more"}
    if user_decision not in valid_decisions:
        errors.append(f"Invalid decision: {user_decision}")
        user_decision = "reject"

    # Extract edits
    edits = raw_response.get("edits", [])
    if not isinstance(edits, list):
        edits = []

    # Extract notes
    user_notes = raw_response.get("user_notes", "")

    # Create structured response
    response: dict[str, Any] = {
        "schema_version": "confirmation_response_v1",
        "job_id": job_id,
        "round_id": round_n,
        "user_decision": user_decision,
        "edits": edits,
        "user_notes": user_notes,
    }

    # Save to file
    conf_dir = _get_confirmation_dir(job_id)
    output_path = conf_dir / f"confirmation_response_round_{round_n}.json"
    response = ConfirmationResponse.model_validate(response).model_dump(mode="json")
    _save_json(response, output_path)

    return {
        "confirmation_response_path": str(output_path),
        "user_decision": user_decision,
        "total_edits": len(edits),
        "errors": errors,
    }


async def merge_user_confirmation(
    state: HumanConfirmationState,
) -> dict[str, Any]:
    """Merge user confirmation with proposed model to create confirmed plan.

    Handles four decision types:
    - approve: Mark all fields as confirmed
    - edit: Apply user edits, mark edited fields as user-provided
      (source_type="user", confidence=1.0)
    - reject: Set status to rejected, stop processing
    - ask_more: Increment round, continue to next round

    Returns dict with all output paths, final status, and unconfirmed_assumptions_count.
    """
    errors: list[str] = []
    job_id = state["job_id"]
    round_n = state.get("human_confirmation_round", 1)

    # Load proposed model completion
    conf_dir = _get_confirmation_dir(job_id)
    proposal_path = conf_dir / "proposed_model_completion.json"
    proposal = _load_json(proposal_path)

    if not proposal:
        errors.append(f"Proposed model completion not found at {proposal_path}")

    # Load confirmation response
    response_path = conf_dir / f"confirmation_response_round_{round_n}.json"
    response = _load_json(response_path)

    if not response:
        errors.append(f"Confirmation response not found at {response_path}")

    # Get user decision
    user_decision = response.get("user_decision", "approve") if response else "approve"

    # Initialize confirmed model plan
    confirmed_plan: dict[str, Any] = {
        "schema_version": "confirmed_model_plan_v1",
        "job_id": job_id,
        "source_query": proposal.get("source_query", "") if proposal else "",
        "domain_profile": "geant4",
        "components": [],
        "sources": [],
        "scoring": [],
        "assumptions_confirmed": False,
        "confirmation_status": "draft",
        "confirmation_history": [],
    }

    confirmed_fields: list[str] = []
    edited_fields: list[str] = []
    rejected_fields: list[str] = []

    # Track all fields requiring confirmation to calculate unconfirmed count
    total_fields_requiring_confirmation: set[str] = set()

    # Handle rejection
    if user_decision == "reject":
        confirmed_plan["confirmation_status"] = "rejected"
        rejected_fields = [
            p["field_path"]
            for comp in (proposal.get("proposed_components", []) if proposal else [])
            for p in comp.get("parameters", [])
        ]

    # Handle ask_more
    elif user_decision == "ask_more":
        confirmed_plan["confirmation_status"] = "ask_more"
        # Keep proposal as-is for next round

    # Handle approve and edit
    else:
        # Process components
        for comp in proposal.get("proposed_components", []) if proposal else []:
            confirmed_comp = {
                "component_id": comp.get("component_id"),
                "component_type": comp.get("component_type"),
                "material_id": comp.get("material_id"),
                "geometry": comp.get("geometry", {}),
                "placement": comp.get("placement", {}),
                "roles": comp.get("roles", []),
                "confirmed_by_user": False,
                "parameters": [],  # Include parameters with metadata
            }

            # Check for edits
            edits = response.get("edits", []) if response else []
            for param in comp.get("parameters", []):
                field_path = param["field_path"]

                # Track fields requiring confirmation
                if param.get("requires_confirmation", False):
                    total_fields_requiring_confirmation.add(field_path)

                # Check if user edited this field
                edit = next((e for e in edits if e["field_path"] == field_path), None)

                if edit:
                    # Apply edit and mark as user-provided
                    _apply_edit_to_component(confirmed_comp, field_path, edit["new_value"])
                    edited_fields.append(field_path)
                    confirmed_comp["confirmed_by_user"] = True
                    # Store parameter with user-provenance metadata
                    confirmed_comp["parameters"].append(
                        {
                            "field_path": field_path,
                            "value": edit["new_value"],
                            "source_type": "user",
                            "confidence": 1.0,
                            "requires_confirmation": False,
                        }
                    )
                elif user_decision == "approve":
                    # Mark as confirmed
                    confirmed_fields.append(field_path)
                    confirmed_comp["confirmed_by_user"] = True
                    # Store parameter with original metadata
                    confirmed_comp["parameters"].append(
                        {
                            "field_path": field_path,
                            "value": param.get("proposed_value"),
                            "source_type": param.get("source_type", "rag"),
                            "confidence": param.get("confidence", 0.8),
                            "requires_confirmation": False,  # Now confirmed
                        }
                    )

            confirmed_plan["components"].append(confirmed_comp)

        # Process sources
        for src in proposal.get("proposed_sources", []) if proposal else []:
            field_path = src["field_path"]

            # Track fields requiring confirmation
            if src.get("requires_confirmation", False):
                total_fields_requiring_confirmation.add(field_path)

            confirmed_src = {
                "source_id": src.get("field_path", "primary").split(".")[-1],
                "confirmed_by_user": False,
            }

            edit = next(
                (
                    e
                    for e in (response.get("edits", []) if response else [])
                    if e["field_path"] == field_path
                ),
                None,
            )

            if edit:
                confirmed_src["proposed_value"] = edit["new_value"]
                confirmed_src["source_type"] = "user"
                confirmed_src["confidence"] = 1.0
                confirmed_src["requires_confirmation"] = False
                edited_fields.append(field_path)
                confirmed_src["confirmed_by_user"] = True
            elif user_decision == "approve":
                confirmed_fields.append(field_path)
                confirmed_src["source_type"] = src.get("source_type", "rag")
                confirmed_src["confidence"] = src.get("confidence", 0.8)
                confirmed_src["requires_confirmation"] = False
                confirmed_src["confirmed_by_user"] = True
                confirmed_src["proposed_value"] = src.get("proposed_value")

            confirmed_plan["sources"].append(confirmed_src)

        # Process scoring
        for sc in proposal.get("proposed_scoring", []) if proposal else []:
            field_path = sc["field_path"]

            # Track fields requiring confirmation
            if sc.get("requires_confirmation", False):
                total_fields_requiring_confirmation.add(field_path)

            confirmed_sc = {
                "scoring_id": sc.get("field_path", "dose").split(".")[-1],
                "confirmed_by_user": False,
            }

            edit = next(
                (
                    e
                    for e in (response.get("edits", []) if response else [])
                    if e["field_path"] == field_path
                ),
                None,
            )

            if edit:
                confirmed_sc["proposed_value"] = edit["new_value"]
                confirmed_sc["source_type"] = "user"
                confirmed_sc["confidence"] = 1.0
                confirmed_sc["requires_confirmation"] = False
                edited_fields.append(field_path)
                confirmed_sc["confirmed_by_user"] = True
            elif user_decision == "approve":
                confirmed_fields.append(field_path)
                confirmed_sc["source_type"] = sc.get("source_type", "rag")
                confirmed_sc["confidence"] = sc.get("confidence", 0.8)
                confirmed_sc["requires_confirmation"] = False
                confirmed_sc["confirmed_by_user"] = True
                confirmed_sc["proposed_value"] = sc.get("proposed_value")

            confirmed_plan["scoring"].append(confirmed_sc)

        # Set confirmation status
        if user_decision == "approve":
            confirmed_plan["confirmation_status"] = "approved"
            confirmed_plan["assumptions_confirmed"] = True
        elif user_decision == "edit":
            confirmed_plan["confirmation_status"] = "edited"
            confirmed_plan["assumptions_confirmed"] = True

    # Calculate remaining unconfirmed assumptions/fields
    # Count = total requiring - (confirmed + edited)
    unconfirmed_count = max(
        0, len(total_fields_requiring_confirmation) - len(confirmed_fields) - len(edited_fields)
    )

    # Save confirmed model plan
    plan_path = conf_dir / "confirmed_model_plan.json"
    _save_json(confirmed_plan, plan_path)

    # Create confirmation record
    record: dict[str, Any] = {
        "schema_version": "confirmation_record_v1",
        "job_id": job_id,
        "total_rounds": round_n,
        "final_status": confirmed_plan["confirmation_status"],
        "confirmed_fields": confirmed_fields,
        "edited_fields": edited_fields,
        "rejected_fields": rejected_fields,
        "remaining_unconfirmed_fields": [],
        "unconfirmed_assumptions_count": unconfirmed_count,
        "confirmation_history": [
            {
                "round_id": round_n,
                "user_decision": user_decision,
                "edits": response.get("edits", []) if response else [],
                "user_notes": response.get("user_notes", "") if response else "",
            }
        ],
        "confirmed_model_plan_path": str(plan_path),
    }

    # Save confirmation record
    record_path = conf_dir / "confirmation_record.json"
    record = ConfirmationRecord.model_validate(record).model_dump(mode="json")
    _save_json(record, record_path)

    # Generate report
    report_path = generate_confirmation_report(record, conf_dir)

    return {
        "confirmation_record_path": str(record_path),
        "confirmed_model_plan_path": str(plan_path),
        "confirmation_report_path": report_path,
        "confirmation_status": confirmed_plan["confirmation_status"],
        "confirmed_fields_count": len(confirmed_fields),
        "edited_fields": edited_fields,
        "edited_fields_count": len(edited_fields),
        "rejected_fields_count": len(rejected_fields),
        "unconfirmed_assumptions_count": unconfirmed_count,
        "errors": errors,
    }


def _apply_edit_to_component(comp: dict[str, Any], field_path: str, new_value: Any) -> None:
    """Apply an edit to a component based on field path.

    Field path format: components.<component_id>.<field>
    or components.<component_id>.geometry.<dim>
    """
    parts = field_path.split(".")

    if len(parts) < 3:
        return

    # Extract component_id and field name
    # parts[0] = "components", parts[1] = component_id, parts[2:] = nested keys

    if len(parts) == 3:
        # Direct field: components.comp_id.material_id
        field_name = parts[2]
        comp[field_name] = new_value
    elif len(parts) >= 4:
        # Nested field: components.comp_id.geometry.x
        nested_key = parts[2]
        if nested_key not in comp:
            comp[nested_key] = {}

        if len(parts) == 4:
            # One level nested: geometry.x
            comp[nested_key][parts[3]] = new_value
        else:
            # Deeper nesting: geometry.size.width
            current = comp[nested_key]
            for key in parts[3:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            current[parts[-1]] = new_value


async def validate_confirmation_completeness(
    state: HumanConfirmationState,
) -> dict[str, Any]:
    """Validate that all required confirmations are complete.

    Checks the confirmed model plan against validation rules:
    - No unconfirmed assumptions should remain
    - All critical fields must be confirmed

    Returns dict with confirmation_status and validation result.
    """
    errors: list[str] = []
    job_id = state["job_id"]
    round_n = state.get("human_confirmation_round", 1)

    # Load confirmed model plan
    conf_dir = _get_confirmation_dir(job_id)
    plan_path = conf_dir / "confirmed_model_plan.json"
    plan = _load_json(plan_path)

    if not plan:
        errors.append(f"Confirmed model plan not found at {plan_path}")
        return {
            "confirmation_status": "failed",
            "validation_passed": False,
            "errors": errors,
        }

    # Run validation
    validation_result = validate_human_confirmation(plan)

    # Determine final status
    current_status = plan.get("confirmation_status", "draft")

    # If rejected or ask_more, keep as-is
    if current_status in {"rejected", "ask_more"}:
        unconfirmed = len(validation_result.unconfirmed_components) + len(
            validation_result.unconfirmed_fields
        )
        return {
            "confirmation_status": current_status,
            "validation_passed": current_status == "rejected",
            "unconfirmed_count": unconfirmed,
            "errors": errors,
        }

    # Check if validation passed
    if validation_result.passed:
        return {
            "confirmation_status": current_status,  # approved or edited
            "validation_passed": True,
            "unconfirmed_count": 0,
            "errors": errors,
        }

    # Validation failed: check if we have rounds left
    if round_n < CONFIRMATION_ROUND_LIMIT:
        unconfirmed = len(validation_result.unconfirmed_components) + len(
            validation_result.unconfirmed_fields
        )
        return {
            "confirmation_status": "pending",
            "validation_passed": False,
            "unconfirmed_count": unconfirmed,
            "unconfirmed_components": validation_result.unconfirmed_components,
            "unconfirmed_fields": validation_result.unconfirmed_fields,
            "next_round": round_n + 1,
            "errors": errors,
        }

    # No rounds left: mark as failed
    unconfirmed = len(validation_result.unconfirmed_components) + len(
        validation_result.unconfirmed_fields
    )
    return {
        "confirmation_status": "failed",
        "validation_passed": False,
        "unconfirmed_count": unconfirmed,
        "unconfirmed_components": validation_result.unconfirmed_components,
        "unconfirmed_fields": validation_result.unconfirmed_fields,
        "validation_errors": validation_result.errors,
        "validation_warnings": validation_result.warnings,
        "errors": errors,
    }
