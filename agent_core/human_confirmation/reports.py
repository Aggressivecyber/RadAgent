"""Report generators for Human Confirmation Subgraph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def generate_confirmation_report(
    record: dict[str, Any],
    output_dir: Path,
) -> str:
    """Generate human_confirmation_report.md from confirmation artifacts.

    Returns the path to the generated report.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    record = _merge_disk_record(record, output_dir)
    proposal = _load_artifact(
        record,
        output_dir,
        path_field="proposed_model_completion_path",
        default_filename="proposed_model_completion.json",
    )
    confirmed_plan = _load_artifact(
        record,
        output_dir,
        path_field="confirmed_model_plan_path",
        default_filename="confirmed_model_plan.json",
    )

    readiness = _codegen_readiness(record, confirmed_plan)
    key_parameters = _collect_key_parameters(proposal, confirmed_plan, record)

    lines = [
        "# Human Confirmation Report",
        "",
        "Readable simulation plan review for human-confirmed Geant4 code generation.",
        "",
        "## Task Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Job ID | {_table_cell(record.get('job_id', 'unknown'))} |",
        f"| Task | {_table_cell(_task_text(proposal, confirmed_plan))} |",
        f"| Simulation object | {_table_cell(_simulation_object(proposal, confirmed_plan))} |",
        f"| Domain profile | {_table_cell(_domain_profile(proposal, confirmed_plan))} |",
        f"| Final status | {_table_cell(record.get('final_status', 'unknown'))} |",
        f"| Total confirmation rounds | {_table_cell(record.get('total_rounds', 0))} |",
        f"| Codegen readiness | {_table_cell(readiness['decision'])} |",
        "",
    ]

    lines.extend(_object_components_materials_sources_scoring(proposal, confirmed_plan, record))
    lines.extend(_key_parameter_table(key_parameters))
    lines.extend(_assumptions_and_risks(proposal, record, key_parameters, readiness))
    lines.extend(_required_user_actions(proposal, record, readiness))
    lines.extend(_confirmation_history(record))
    lines.extend(_codegen_readiness_section(record, confirmed_plan, readiness))

    report_path = output_dir / "human_confirmation_report.md"
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return str(report_path)


def _merge_disk_record(record: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    disk_record = _load_json(output_dir / "confirmation_record.json")
    if not disk_record:
        return dict(record)
    merged = dict(disk_record)
    merged.update(record)
    return merged


def _load_artifact(
    record: dict[str, Any],
    output_dir: Path,
    *,
    path_field: str,
    default_filename: str,
) -> dict[str, Any]:
    candidate_paths: list[Path] = []
    field_value = record.get(path_field)
    if isinstance(field_value, str) and field_value:
        candidate_paths.extend(_resolve_candidate_paths(field_value, output_dir))
    candidate_paths.append(output_dir / default_filename)

    for path in candidate_paths:
        loaded = _load_json(path)
        if loaded:
            return loaded
    return {}


def _resolve_candidate_paths(path_value: str, output_dir: Path) -> list[Path]:
    path = Path(path_value)
    if path.is_absolute():
        return [path]
    return [output_dir / path, path]


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _task_text(proposal: dict[str, Any], confirmed_plan: dict[str, Any]) -> str:
    return (
        proposal.get("source_query")
        or confirmed_plan.get("source_query")
        or "No source query recorded."
    )


def _domain_profile(proposal: dict[str, Any], confirmed_plan: dict[str, Any]) -> str:
    return proposal.get("domain_profile") or confirmed_plan.get("domain_profile") or "unknown"


def _simulation_object(proposal: dict[str, Any], confirmed_plan: dict[str, Any]) -> str:
    components = _components(proposal, confirmed_plan)
    if not components:
        return "No components recorded."

    prioritized: list[str] = []
    fallback: list[str] = []
    for component in components:
        component_id = component.get("component_id") or "unnamed_component"
        roles = [str(role).lower() for role in component.get("roles", [])]
        label = f"{component_id} ({component.get('component_type', 'component')})"
        if any(role in {"target", "phantom", "detector", "scoring_volume"} for role in roles):
            prioritized.append(label)
        else:
            fallback.append(label)
    return ", ".join(prioritized or fallback)


def _object_components_materials_sources_scoring(
    proposal: dict[str, Any],
    confirmed_plan: dict[str, Any],
    record: dict[str, Any],
) -> list[str]:
    lines = [
        "## Object, Components, Materials, Sources, Scoring",
        "",
    ]

    components = _components(proposal, confirmed_plan)
    lines.extend(_components_section(components, record))
    lines.extend(_materials_section(components, record))
    lines.extend(
        _grouped_parameter_section("Sources", _source_parameters(proposal, confirmed_plan), record)
    )
    lines.extend(
        _grouped_parameter_section("Scoring", _scoring_parameters(proposal, confirmed_plan), record)
    )
    return lines


def _components_section(components: list[dict[str, Any]], record: dict[str, Any]) -> list[str]:
    lines = ["### Components", ""]
    if not components:
        return lines + ["- No component artifact was available.", ""]

    lines.extend(
        [
            "| Component | Type | Material | Geometry | Placement | Roles | Confirmation |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for component in components:
        component_id = component.get("component_id") or "unnamed_component"
        material_field = f"components.{component_id}.material_id"
        material = _field_value_from_record(material_field, record) or component.get("material_id")
        lines.append(
            "| "
            f"{_table_cell(component_id)} | "
            f"{_table_cell(component.get('component_type', 'unknown'))} | "
            f"{_table_cell(material or 'not specified')} | "
            f"{_table_cell(_format_value(component.get('geometry') or 'not specified'))} | "
            f"{_table_cell(_format_value(component.get('placement') or 'not specified'))} | "
            f"{_table_cell(_format_value(component.get('roles') or []))} | "
            f"{_table_cell(_component_confirmation(component_id, record))} |"
        )
    return lines + [""]


def _materials_section(components: list[dict[str, Any]], record: dict[str, Any]) -> list[str]:
    lines = ["### Materials", ""]
    material_usage: dict[str, list[str]] = {}
    for component in components:
        component_id = component.get("component_id") or "unnamed_component"
        material_field = f"components.{component_id}.material_id"
        material = _field_value_from_record(material_field, record) or component.get("material_id")
        if material:
            material_usage.setdefault(str(material), []).append(str(component_id))

    if not material_usage:
        return lines + ["- No material assignments were available.", ""]

    lines.extend(["| Material | Used by | Confirmation |", "| --- | --- | --- |"])
    for material, component_ids in sorted(material_usage.items()):
        confirmations = {
            _component_confirmation(component_id, record) for component_id in component_ids
        }
        lines.append(
            "| "
            f"{_table_cell(material)} | "
            f"{_table_cell(', '.join(component_ids))} | "
            f"{_table_cell(', '.join(sorted(confirmations)))} |"
        )
    return lines + [""]


def _grouped_parameter_section(
    title: str,
    parameters: list[dict[str, Any]],
    record: dict[str, Any],
) -> list[str]:
    lines = [f"### {title}", ""]
    if not parameters:
        return lines + [f"- No {title.lower()} artifact was available.", ""]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for parameter in parameters:
        grouped.setdefault(
            _entity_id_from_field(parameter.get("field_path", ""), title), []
        ).append(
            parameter,
        )

    lines.extend(["| ID | Parameters | Confirmation |", "| --- | --- | --- |"])
    for entity_id, entity_parameters in sorted(grouped.items()):
        parameter_summary = "; ".join(
            f"{_field_name(p.get('field_path', ''))}={_format_value(_parameter_value(p, record))}"
            for p in entity_parameters
        )
        confirmation_summary = _parameter_group_confirmation(entity_parameters, record)
        lines.append(
            "| "
            f"{_table_cell(entity_id)} | "
            f"{_table_cell(parameter_summary)} | "
            f"{_table_cell(confirmation_summary)} |"
        )
    return lines + [""]


def _key_parameter_table(parameters: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Key Parameter Table",
        "",
        "| Parameter | Value | Unit | Source | Confidence | Confirmation |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not parameters:
        lines.append("| No key parameters available | n/a | n/a | n/a | n/a | unavailable |")
        return lines + [""]

    for parameter in parameters:
        lines.append(
            "| "
            f"{_table_cell(parameter.get('field_path', 'unknown'))} | "
            f"{_table_cell(_format_value(parameter.get('value')))} | "
            f"{_table_cell(parameter.get('unit') or 'n/a')} | "
            f"{_table_cell(parameter.get('source') or 'unknown')} | "
            f"{_table_cell(_format_confidence(parameter.get('confidence')))} | "
            f"{_table_cell(parameter.get('confirmation') or 'unknown')} |"
        )
    return lines + [""]


def _assumptions_and_risks(
    proposal: dict[str, Any],
    record: dict[str, Any],
    parameters: list[dict[str, Any]],
    readiness: dict[str, str],
) -> list[str]:
    lines = ["## Assumptions and Risks", ""]

    assumptions = _string_list(proposal.get("assumptions", []))
    missing_information = _string_list(proposal.get("missing_information", []))
    low_confidence = [
        parameter
        for parameter in parameters
        if _is_low_confidence(parameter.get("confidence"))
        and parameter.get("confirmation") not in {"confirmed by user", "edited by user"}
    ]

    if assumptions:
        lines.append("### Assumptions")
        lines.extend(f"- {_plain_text(assumption)}" for assumption in assumptions)
        lines.append("")

    if missing_information:
        lines.append("### Missing Information")
        lines.extend(f"- {_plain_text(item)}" for item in missing_information)
        lines.append("")

    risk_lines = []
    for field_path in _string_list(record.get("remaining_unconfirmed_fields", [])):
        risk_lines.append(f"Unconfirmed field remains: {field_path}")
    for field_path in _string_list(record.get("rejected_fields", [])):
        risk_lines.append(f"Rejected field blocks reuse: {field_path}")
    if record.get("unconfirmed_assumptions_count", 0):
        risk_lines.append(
            f"Unconfirmed assumption count: {record.get('unconfirmed_assumptions_count')}"
        )
    for parameter in low_confidence:
        risk_lines.append(
            "Low-confidence unconfirmed parameter: "
            f"{parameter.get('field_path')} ({_format_confidence(parameter.get('confidence'))})"
        )
    if readiness["status"] != "ready":
        risk_lines.append(readiness["reason"])

    lines.append("### Risks")
    if risk_lines:
        lines.extend(f"- {_plain_text(risk)}" for risk in dict.fromkeys(risk_lines))
    else:
        lines.append("- No blocking risks recorded in human confirmation artifacts.")
    lines.append("")
    return lines


def _required_user_actions(
    proposal: dict[str, Any],
    record: dict[str, Any],
    readiness: dict[str, str],
) -> list[str]:
    lines = ["## Required User Actions", ""]
    final_status = str(record.get("final_status", "unknown"))
    actions: list[str] = []

    if readiness["status"] == "ready":
        actions.append("No additional user action is required before code generation.")
    elif final_status == "ask_more":
        actions.append("Answer the pending follow-up confirmation questions.")
    elif final_status == "rejected":
        actions.append("Revise or replace the simulation plan before code generation.")
    elif final_status == "failed":
        actions.append("Resolve failed or missing confirmation artifacts before code generation.")
    else:
        actions.append("Complete human confirmation before code generation.")

    remaining_fields = _string_list(record.get("remaining_unconfirmed_fields", []))
    if remaining_fields:
        actions.append("Confirm or edit remaining fields: " + ", ".join(remaining_fields))

    missing_information = _string_list(proposal.get("missing_information", []))
    if readiness["status"] != "ready" and missing_information:
        actions.append("Provide missing simulation information where it affects the model.")

    lines.extend(f"- {_plain_text(action)}" for action in dict.fromkeys(actions))
    lines.append("")
    return lines


def _confirmation_history(record: dict[str, Any]) -> list[str]:
    lines = ["## Confirmation History", ""]
    history = record.get("confirmation_history", [])
    if not isinstance(history, list) or not history:
        return lines + ["- No confirmation history recorded.", ""]

    lines.extend(["| Round | Decision | Edits | Notes |", "| --- | --- | --- | --- |"])
    for index, entry in enumerate(history, 1):
        if not isinstance(entry, dict):
            continue
        edits = entry.get("edits", [])
        lines.append(
            "| "
            f"{_table_cell(entry.get('round_id', index))} | "
            f"{_table_cell(entry.get('user_decision', 'unknown'))} | "
            f"{_table_cell(_format_edits(edits))} | "
            f"{_table_cell(entry.get('user_notes') or 'n/a')} |"
        )
    lines.append("")
    return lines


def _codegen_readiness_section(
    record: dict[str, Any],
    confirmed_plan: dict[str, Any],
    readiness: dict[str, str],
) -> list[str]:
    plan_path = record.get("confirmed_model_plan_path") or "not recorded"
    plan_status = _table_cell(confirmed_plan.get("confirmation_status", "missing"))
    assumptions_count = _table_cell(record.get("unconfirmed_assumptions_count", 0))
    remaining_fields = _table_cell(_count(record.get("remaining_unconfirmed_fields")))
    lines = [
        "## Codegen Readiness",
        "",
        "| Check | Result |",
        "| --- | --- |",
        f"| Readiness decision | {_table_cell(readiness['decision'])} |",
        f"| Reason | {_table_cell(readiness['reason'])} |",
        f"| Confirmation status | {_table_cell(record.get('final_status', 'unknown'))} |",
        f"| Confirmed plan status | {plan_status} |",
        f"| Unconfirmed assumptions | {assumptions_count} |",
        f"| Remaining unconfirmed fields | {remaining_fields} |",
        f"| Confirmed model plan | {_table_cell(plan_path)} |",
        "",
    ]
    return lines


def _collect_key_parameters(
    proposal: dict[str, Any],
    confirmed_plan: dict[str, Any],
    record: dict[str, Any],
) -> list[dict[str, Any]]:
    proposal_parameters = _proposal_parameters(proposal)
    if proposal_parameters:
        return [_parameter_row(parameter, record) for parameter in proposal_parameters]

    plan_parameters = _plan_parameters(confirmed_plan)
    return [_parameter_row(parameter, record) for parameter in plan_parameters]


def _proposal_parameters(proposal: dict[str, Any]) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for component in proposal.get("proposed_components", []):
        if not isinstance(component, dict):
            continue
        for parameter in component.get("parameters", []):
            if isinstance(parameter, dict):
                parameters.append(parameter)
    parameters.extend(_source_parameters(proposal, {}))
    parameters.extend(_scoring_parameters(proposal, {}))
    return parameters


def _source_parameters(
    proposal: dict[str, Any],
    confirmed_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    parameters = [
        parameter
        for parameter in proposal.get("proposed_sources", [])
        if isinstance(parameter, dict)
    ]
    if parameters:
        return parameters
    return _flat_plan_entities(confirmed_plan.get("sources", []), "sources", "source_id")


def _scoring_parameters(
    proposal: dict[str, Any],
    confirmed_plan: dict[str, Any],
) -> list[dict[str, Any]]:
    parameters = [
        parameter
        for parameter in proposal.get("proposed_scoring", [])
        if isinstance(parameter, dict)
    ]
    if parameters:
        return parameters
    return _flat_plan_entities(confirmed_plan.get("scoring", []), "scoring", "scoring_id")


def _plan_parameters(confirmed_plan: dict[str, Any]) -> list[dict[str, Any]]:
    parameters: list[dict[str, Any]] = []
    for component in confirmed_plan.get("components", []):
        if not isinstance(component, dict):
            continue
        parameters.extend(
            parameter
            for parameter in component.get("parameters", [])
            if isinstance(parameter, dict)
        )
    parameters.extend(_source_parameters({}, confirmed_plan))
    parameters.extend(_scoring_parameters({}, confirmed_plan))
    return parameters


def _parameter_row(parameter: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    field_path = parameter.get("field_path", "unknown")
    edit_value = _field_value_from_record(field_path, record)
    value = edit_value if edit_value is not None else _parameter_value(parameter, record)
    return {
        "field_path": field_path,
        "value": value,
        "unit": _field_unit_from_record(field_path, record) or parameter.get("unit"),
        "source": _parameter_source(parameter),
        "confidence": parameter.get("confidence"),
        "confirmation": _field_confirmation(field_path, parameter, record),
    }


def _parameter_value(parameter: dict[str, Any], record: dict[str, Any]) -> Any:
    field_path = parameter.get("field_path", "")
    edit_value = _field_value_from_record(field_path, record)
    if edit_value is not None:
        return edit_value
    if "value" in parameter:
        return parameter.get("value")
    return parameter.get("proposed_value")


def _parameter_source(parameter: dict[str, Any]) -> str:
    source_type = parameter.get("source_type") or parameter.get("source") or "unknown"
    source_ref = parameter.get("source_ref")
    reason = parameter.get("reason")
    if source_ref:
        return f"{source_type}: {_truncate(_format_value(source_ref), 56)}"
    if reason:
        return f"{source_type}: {_truncate(_format_value(reason), 56)}"
    return str(source_type)


def _components(proposal: dict[str, Any], confirmed_plan: dict[str, Any]) -> list[dict[str, Any]]:
    components = [
        component
        for component in proposal.get("proposed_components", [])
        if isinstance(component, dict)
    ]
    if components:
        return components
    return [
        component
        for component in confirmed_plan.get("components", [])
        if isinstance(component, dict)
    ]


def _flat_plan_entities(
    entities: Any,
    group_name: str,
    id_field: str,
) -> list[dict[str, Any]]:
    if not isinstance(entities, list):
        return []
    parameters: list[dict[str, Any]] = []
    metadata_fields = {id_field, "confirmed_by_user", "requires_confirmation"}
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        entity_id = entity.get(id_field) or "primary"
        for key, value in entity.items():
            if key in metadata_fields:
                continue
            parameters.append(
                {
                    "field_path": f"{group_name}.{entity_id}.{key}",
                    "proposed_value": value,
                    "source_type": entity.get("source_type", "confirmed_plan"),
                    "confidence": entity.get("confidence"),
                    "requires_confirmation": entity.get("requires_confirmation", False),
                }
            )
    return parameters


def _field_confirmation(
    field_path: str,
    parameter: dict[str, Any],
    record: dict[str, Any],
) -> str:
    if field_path in set(_string_list(record.get("edited_fields", []))):
        return "edited by user"
    if field_path in set(_string_list(record.get("confirmed_fields", []))):
        return "confirmed by user"
    if field_path in set(_string_list(record.get("rejected_fields", []))):
        return "rejected"
    if field_path in set(_string_list(record.get("remaining_unconfirmed_fields", []))):
        return "unconfirmed"
    if field_path in _edits_by_field(record):
        return "edited by user"
    if record.get("final_status") == "rejected" and parameter.get("requires_confirmation"):
        return "rejected"
    if parameter.get("requires_confirmation") is False:
        return "not required"
    return "needs confirmation"


def _component_confirmation(component_id: str, record: dict[str, Any]) -> str:
    prefix = f"components.{component_id}."
    statuses = []
    for field_path in _string_list(record.get("edited_fields", [])):
        if field_path.startswith(prefix):
            statuses.append("edited by user")
    for field_path in _string_list(record.get("confirmed_fields", [])):
        if field_path.startswith(prefix):
            statuses.append("confirmed by user")
    for field_path in _string_list(record.get("remaining_unconfirmed_fields", [])):
        if field_path.startswith(prefix):
            statuses.append("unconfirmed")
    for field_path in _string_list(record.get("rejected_fields", [])):
        if field_path.startswith(prefix):
            statuses.append("rejected")
    return ", ".join(dict.fromkeys(statuses)) if statuses else "not requested"


def _parameter_group_confirmation(
    parameters: list[dict[str, Any]],
    record: dict[str, Any],
) -> str:
    statuses = [_field_confirmation(p.get("field_path", ""), p, record) for p in parameters]
    return ", ".join(dict.fromkeys(statuses))


def _field_value_from_record(field_path: str, record: dict[str, Any]) -> Any:
    edit = _edits_by_field(record).get(field_path)
    if edit:
        return edit.get("new_value")
    return None


def _field_unit_from_record(field_path: str, record: dict[str, Any]) -> str | None:
    edit = _edits_by_field(record).get(field_path)
    if edit and isinstance(edit.get("unit"), str):
        return edit["unit"]
    return None


def _edits_by_field(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    edits_by_field: dict[str, dict[str, Any]] = {}
    history = record.get("confirmation_history", [])
    if not isinstance(history, list):
        return edits_by_field
    for entry in history:
        if not isinstance(entry, dict):
            continue
        edits = entry.get("edits", [])
        if not isinstance(edits, list):
            continue
        for edit in edits:
            if isinstance(edit, dict) and edit.get("field_path"):
                edits_by_field[str(edit["field_path"])] = edit
    return edits_by_field


def _codegen_readiness(
    record: dict[str, Any],
    confirmed_plan: dict[str, Any],
) -> dict[str, str]:
    final_status = str(record.get("final_status", "unknown"))
    remaining = _count(record.get("remaining_unconfirmed_fields"))
    unconfirmed_assumptions = int(record.get("unconfirmed_assumptions_count") or 0)
    plan_status = str(confirmed_plan.get("confirmation_status", "missing"))
    has_plan = bool(confirmed_plan)

    if final_status in {"approved", "edited"} and remaining == 0 and unconfirmed_assumptions == 0:
        if has_plan and plan_status in {"approved", "edited"}:
            return {
                "status": "ready",
                "decision": "READY - code generation can proceed",
                "reason": "Human confirmation completed and confirmed model plan is available.",
            }
        if not has_plan:
            return {
                "status": "blocked",
                "decision": "BLOCKED - confirmed model plan missing",
                "reason": (
                    "The confirmation record is complete but confirmed_model_plan.json "
                    "is missing."
                ),
            }

    if final_status == "ask_more":
        reason = "User requested additional clarification; confirmation is not complete."
    elif final_status == "rejected":
        reason = "User rejected the proposed simulation plan."
    elif final_status == "failed":
        reason = "Human confirmation failed before a complete plan was approved."
    elif remaining or unconfirmed_assumptions:
        reason = "Unconfirmed fields or assumptions remain."
    else:
        reason = f"Final confirmation status is {final_status}."

    return {
        "status": "blocked",
        "decision": "BLOCKED - code generation must not proceed",
        "reason": reason,
    }


def _entity_id_from_field(field_path: str, title: str) -> str:
    parts = field_path.split(".")
    if len(parts) >= 2:
        return parts[1]
    return title.lower()


def _field_name(field_path: str) -> str:
    parts = field_path.split(".")
    return parts[-1] if parts else field_path


def _format_edits(edits: Any) -> str:
    if not isinstance(edits, list) or not edits:
        return "none"
    rendered = []
    for edit in edits:
        if not isinstance(edit, dict):
            continue
        field_path = edit.get("field_path", "?")
        new_value = _format_value(edit.get("new_value"))
        unit = f" {edit['unit']}" if edit.get("unit") else ""
        rendered.append(f"{field_path}={new_value}{unit}")
    return "; ".join(rendered) if rendered else "none"


def _format_value(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return _truncate(value.replace("\n", " "))
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    try:
        return _truncate(json.dumps(value, ensure_ascii=True, sort_keys=True))
    except TypeError:
        return _truncate(str(value))


def _format_confidence(value: Any) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.2f}"
    return "unknown"


def _is_low_confidence(value: Any) -> bool:
    return isinstance(value, int | float) and float(value) < 0.7


def _table_cell(value: Any) -> str:
    return _plain_text(_format_value(value)).replace("|", "\\|")


def _plain_text(value: Any) -> str:
    return str(value).replace("\n", " ").strip()


def _truncate(value: str, limit: int = 120) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0
