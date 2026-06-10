"""Gate 20 credibility and plausibility assessment."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from agent_core.gates.output_quality import REQUIRED_G4_OUTPUTS, inspect_g4_output_quality
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_output_dir

from .base_gates import gate_name
from .schemas import GateSubgraphState

GATE_ID = 20
_FAILED_STATUSES = {"fail", "block", "blocked"}
_PASS_VERDICTS = {"supported", "plausible", "pass", "passed"}
_WARNING_VERDICTS = {"uncertain", "unavailable", "warning", "unknown"}
_FAIL_VERDICTS = {"conflicting", "conflict", "fail", "failed"}
_BLOCK_VERDICTS = {"invalid", "block", "blocked"}


async def run_credibility_gate(state: GateSubgraphState) -> dict[str, Any]:
    """Run Gate 20 after deterministic output gates and before finalization."""
    gate_results: list[dict[str, Any]] = list(state.get("gate_results", []))
    failed: list[str] = list(state.get("failed_gates", []))

    job_id = state.get("job_id", "unknown")
    output_dir = get_output_dir(job_id)
    smoke_result, smoke_warning = _read_optional_json(output_dir / "smoke_simulation_result.json")
    output_quality = inspect_g4_output_quality(output_dir, smoke_result=smoke_result)
    deterministic = _deterministic_assessment(
        job_id=job_id,
        output_dir=output_dir,
        output_quality=output_quality,
        smoke_result=smoke_result,
        smoke_warning=smoke_warning,
    )

    prior_failures = _prior_critical_failures(gate_results)
    if prior_failures:
        warning = (
            "Credibility assessment uncertain because prior critical gates failed: "
            + ", ".join(_gate_label(gate) for gate in prior_failures[:5])
        )
        gate_results.append(
            _gate_entry(
                status="warning",
                checked_items=[
                    *deterministic["checked_items"],
                    {"item": "prior critical gates passed", "result": "warning"},
                ],
                failed_items=[],
                warnings=[warning, *deterministic["warnings"]],
                evidence=deterministic["evidence"],
                file_paths=deterministic["file_paths"],
                message=(
                    "Credibility assessment uncertain; earlier critical failures take "
                    "precedence"
                ),
                metrics=deterministic["metrics"],
            )
        )
        return {"gate_results": gate_results, "failed_gates": failed}

    deterministic_verdict = str(deterministic["verdict"])
    if deterministic_verdict in {"unavailable", "invalid", "conflicting"}:
        status = _status_for_verdict(deterministic_verdict)
        gate_results.append(
            _gate_entry(
                status=status,
                checked_items=deterministic["checked_items"],
                failed_items=deterministic["failed_items"],
                warnings=deterministic["warnings"],
                evidence=deterministic["evidence"],
                file_paths=deterministic["file_paths"],
                message=str(deterministic["message"]),
                metrics=deterministic["metrics"],
            )
        )
        if status in {"fail", "block"}:
            failed.append(gate_name(GATE_ID))
        return {"gate_results": gate_results, "failed_gates": failed}

    model_assessment = await _call_model_assessor(state, deterministic)
    status, message, warnings, failed_items = _merge_assessments(
        deterministic=deterministic,
        model_assessment=model_assessment,
    )

    gate_results.append(
        _gate_entry(
            status=status,
            checked_items=[
                *deterministic["checked_items"],
                {
                    "item": "LITE model credibility assessment",
                    "result": "pass" if model_assessment["usable"] else "warning",
                },
            ],
            failed_items=failed_items,
            warnings=warnings,
            evidence=[
                *deterministic["evidence"],
                *model_assessment["evidence"],
            ],
            file_paths=deterministic["file_paths"],
            message=message,
            metrics={
                **deterministic["metrics"],
                "model_verdict": model_assessment["verdict"],
            },
        )
    )
    if status in {"fail", "block"}:
        failed.append(gate_name(GATE_ID))
    return {"gate_results": gate_results, "failed_gates": failed}


def _deterministic_assessment(
    *,
    job_id: str,
    output_dir: Path,
    output_quality: Any,
    smoke_result: dict[str, Any],
    smoke_warning: str,
) -> dict[str, Any]:
    checked_items: list[dict[str, str]] = []
    failed_items: list[str] = []
    warnings: list[str] = []
    evidence: list[str] = [f"output_dir: {output_dir}"]
    file_paths: list[str] = []
    metrics: dict[str, Any] = dict(output_quality.metrics)

    if smoke_warning:
        warnings.append(smoke_warning)

    if not output_dir.is_dir():
        return {
            "verdict": "unavailable",
            "checked_items": [{"item": "simulation output directory exists", "result": "warning"}],
            "failed_items": [],
            "warnings": ["Simulation output directory unavailable"],
            "evidence": evidence,
            "file_paths": [],
            "metrics": metrics,
            "message": "Credibility assessment unavailable; no simulation output directory",
        }

    missing_outputs = set(output_quality.metrics.get("missing_outputs", []))
    checked_items.extend(
        {
            "item": f"{name} present",
            "result": "fail" if name in missing_outputs else "pass",
        }
        for name in REQUIRED_G4_OUTPUTS
    )
    file_paths = [
        str(output_dir / name)
        for name in REQUIRED_G4_OUTPUTS
        if (output_dir / name).is_file()
    ]

    summary, summary_error = _read_required_json(output_dir / "g4_summary.json")
    provenance, provenance_error = _read_required_json(output_dir / "provenance.json")
    json_errors = [error for error in (summary_error, provenance_error) if error]
    if json_errors:
        checked_items.append({"item": "required JSON artifacts parse", "result": "fail"})
        failed_items.extend(json_errors)
        return _assessment(
            "invalid",
            checked_items,
            failed_items,
            warnings,
            evidence,
            file_paths,
            metrics,
            "; ".join(json_errors),
        )

    quality_errors = list(output_quality.errors)
    checked_items.append(
        {
            "item": "output quality contract",
            "result": "pass" if not quality_errors else "fail",
        }
    )
    if quality_errors:
        failed_items.extend(quality_errors[:8])
        return _assessment(
            "invalid",
            checked_items,
            failed_items,
            warnings,
            evidence,
            file_paths,
            metrics,
            "; ".join(quality_errors[:5]),
        )

    conflicts = _metadata_conflicts(
        job_id=job_id,
        summary=summary,
        provenance=provenance,
        smoke_result=smoke_result,
    )
    checked_items.append(
        {
            "item": "summary/provenance/smoke metadata consistency",
            "result": "pass" if not conflicts else "fail",
        }
    )
    if conflicts:
        failed_items.extend(conflicts)
        return _assessment(
            "conflicting",
            checked_items,
            failed_items,
            warnings,
            evidence,
            file_paths,
            metrics,
            "; ".join(conflicts[:5]),
        )

    event_metrics = _event_table_metrics(output_dir / "event_table.csv")
    metrics.update(event_metrics)
    if metrics.get("event_table_nonzero_rows", 0) == 0:
        warnings.append("event_table.csv contains no non-zero event rows")

    edep_sum = _as_float(metrics.get("edep_3d_positive_sum"))
    dose_sum = _as_float(metrics.get("dose_3d_positive_sum"))
    checked_items.append(
        {
            "item": "non-zero deposited energy and dose signals",
            "result": "pass" if edep_sum > 0.0 and dose_sum > 0.0 else "warning",
        }
    )
    if warnings:
        return _assessment(
            "uncertain",
            checked_items,
            [],
            warnings,
            evidence,
            file_paths,
            metrics,
            "; ".join(warnings[:5]),
        )

    return _assessment(
        "plausible",
        checked_items,
        [],
        [],
        evidence,
        file_paths,
        metrics,
        "Output artifacts are structurally valid and physically plausible",
    )


async def _call_model_assessor(
    state: GateSubgraphState,
    deterministic: dict[str, Any],
) -> dict[str, Any]:
    job_id = state.get("job_id", "unknown")
    try:
        result = await get_model_gateway().call(
            task=ModelTask.CREDIBILITY_ASSESSMENT,
            tier=ModelTier.LITE,
            system_prompt=_MODEL_SYSTEM_PROMPT,
            user_prompt=_model_user_prompt(state, deterministic),
            response_format="json",
            temperature=0.0,
            max_tokens=800,
            metadata={
                "job_id": job_id,
                "module_name": "gate_20_credibility",
            },
        )
    except Exception as exc:
        return _model_unavailable(f"Credibility model call raised: {exc}")

    if result.error:
        return _model_unavailable(f"Credibility model call failed: {result.error}")
    parsed = result.parsed_json if isinstance(result.parsed_json, dict) else None
    if not parsed:
        return _model_unavailable("Credibility model did not return parseable JSON")

    verdict = _normalize_verdict(parsed.get("verdict", parsed.get("status")))
    if verdict == "unavailable":
        return _model_unavailable(
            "Credibility model returned an unavailable or unrecognized verdict",
            evidence=[
                (
                    "model_response: "
                    f"{json.dumps(parsed, ensure_ascii=False, default=str)[:500]}"
                )
            ],
        )

    warnings = [str(item) for item in parsed.get("warnings", []) if str(item).strip()]
    rationale = str(parsed.get("rationale") or parsed.get("message") or verdict)
    return {
        "verdict": verdict,
        "usable": True,
        "warnings": warnings,
        "rationale": rationale,
        "evidence": [f"model_verdict: {verdict}", f"model_rationale: {rationale}"],
    }


def _merge_assessments(
    *,
    deterministic: dict[str, Any],
    model_assessment: dict[str, Any],
) -> tuple[str, str, list[str], list[str]]:
    warnings = [
        *deterministic["warnings"],
        *model_assessment["warnings"],
    ]

    deterministic_verdict = str(deterministic["verdict"])
    if deterministic_verdict == "uncertain":
        message = "Credibility assessment uncertain: " + str(deterministic["message"])
        if model_assessment["usable"]:
            message += f"; model verdict: {model_assessment['verdict']}"
        return "warning", message, warnings, []

    model_verdict = str(model_assessment["verdict"])
    if not model_assessment["usable"]:
        return (
            "warning",
            "Credibility assessment unavailable from model review",
            warnings,
            [],
        )

    status = _status_for_verdict(model_verdict)
    if status == "pass":
        return "pass", "Credibility assessment supported/plausible", warnings, []
    if status == "warning":
        return "warning", "Credibility assessment uncertain", warnings, []
    if status == "fail":
        message = str(model_assessment["rationale"])
        return "fail", message, warnings, [message]
    message = str(model_assessment["rationale"])
    return "block", message, warnings, [message]


def _assessment(
    verdict: str,
    checked_items: list[dict[str, str]],
    failed_items: list[str],
    warnings: list[str],
    evidence: list[str],
    file_paths: list[str],
    metrics: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "checked_items": checked_items,
        "failed_items": failed_items,
        "warnings": warnings,
        "evidence": evidence,
        "file_paths": file_paths,
        "metrics": metrics,
        "message": message,
    }


def _gate_entry(
    *,
    status: str,
    checked_items: list[dict[str, str]],
    failed_items: list[str],
    warnings: list[str],
    evidence: list[str],
    file_paths: list[str],
    message: str,
    metrics: dict[str, Any],
) -> dict[str, Any]:
    return {
        "gate_id": GATE_ID,
        "name": gate_name(GATE_ID),
        "status": status,
        "checked_items": checked_items,
        "passed_items": [item["item"] for item in checked_items if item.get("result") == "pass"],
        "failed_items": failed_items if status in {"fail", "block"} else [],
        "warnings": warnings,
        "evidence": evidence,
        "file_paths": file_paths,
        "message": message,
        "metrics": metrics,
    }


def _status_for_verdict(verdict: str) -> str:
    normalized = _normalize_verdict(verdict)
    if normalized in _PASS_VERDICTS:
        return "pass"
    if normalized in _FAIL_VERDICTS:
        return "fail"
    if normalized in _BLOCK_VERDICTS:
        return "block"
    return "warning"


def _normalize_verdict(value: Any) -> str:
    verdict = str(value or "").strip().lower()
    if verdict in _PASS_VERDICTS:
        return "plausible" if verdict == "pass" or verdict == "passed" else verdict
    if verdict in _WARNING_VERDICTS:
        return "unavailable" if verdict == "unknown" else verdict
    if verdict in _FAIL_VERDICTS:
        return "conflicting" if verdict in {"conflict", "fail", "failed"} else verdict
    if verdict in _BLOCK_VERDICTS:
        return "invalid" if verdict in {"block", "blocked"} else verdict
    return "unavailable"


def _prior_critical_failures(gate_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        gate
        for gate in gate_results
        if int(gate.get("gate_id", -1)) < GATE_ID
        and gate.get("critical", True) is not False
        and gate.get("status") in _FAILED_STATUSES
    ]


def _gate_label(gate: dict[str, Any]) -> str:
    return f"Gate {gate.get('gate_id')}: {gate.get('name', gate_name(int(gate.get('gate_id', 0))))}"


def _read_required_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{path.name} is not valid JSON: {exc}"
    if not isinstance(data, dict):
        return {}, f"{path.name} must contain a JSON object"
    return data, ""


def _read_optional_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, ""
    data, error = _read_required_json(path)
    if error:
        return {}, f"{path.name} could not be used for credibility checks: {error}"
    return data, ""


def _metadata_conflicts(
    *,
    job_id: str,
    summary: dict[str, Any],
    provenance: dict[str, Any],
    smoke_result: dict[str, Any],
) -> list[str]:
    conflicts: list[str] = []
    for artifact, payload in (("g4_summary.json", summary), ("provenance.json", provenance)):
        artifact_job_id = str(payload.get("job_id") or "").strip()
        if artifact_job_id and artifact_job_id != job_id:
            conflicts.append(f"{artifact} job_id {artifact_job_id!r} does not match {job_id!r}")

    if summary.get("smoke_success") is False and smoke_result.get("success") is True:
        conflicts.append("g4_summary.json reports smoke failure but smoke result reports success")
    if summary.get("smoke_success") is True and smoke_result.get("success") is False:
        conflicts.append("g4_summary.json reports smoke success but smoke result reports failure")
    return conflicts


def _event_table_metrics(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return {}
    return {
        "event_table_edep_sum": sum(_as_float(row.get("edep_MeV")) for row in rows),
        "event_table_dose_sum": sum(_as_float(row.get("dose_Gy")) for row in rows),
    }


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _model_user_prompt(state: GateSubgraphState, deterministic: dict[str, Any]) -> str:
    payload = {
        "job_id": state.get("job_id", "unknown"),
        "task_spec": _compact_dict(state.get("task_spec", {}), limit=2500),
        "model_ir_summary": _model_ir_summary(state.get("g4_model_ir", {})),
        "deterministic_assessment": {
            "verdict": deterministic["verdict"],
            "warnings": deterministic["warnings"],
            "metrics": deterministic["metrics"],
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


def _compact_dict(value: Any, *, limit: int) -> Any:
    if not isinstance(value, dict):
        return value
    encoded = json.dumps(value, ensure_ascii=False, default=str)
    if len(encoded) <= limit:
        return value
    return {"truncated_json": encoded[:limit]}


def _model_ir_summary(model_ir: Any) -> dict[str, Any]:
    if not isinstance(model_ir, dict):
        return {}
    components = model_ir.get("components", [])
    materials = model_ir.get("materials", [])
    sources = model_ir.get("sources", [])
    scoring = model_ir.get("scoring", [])
    physics = model_ir.get("physics", {})
    return {
        "target_system": model_ir.get("target_system"),
        "modeling_mode": model_ir.get("modeling_mode"),
        "component_ids": _ids(components, "component_id"),
        "material_ids": _ids(materials, "material_id"),
        "source_particles": [
            str(source.get("particle_type"))
            for source in sources
            if isinstance(source, dict) and source.get("particle_type")
        ][:8],
        "scoring_quantities": [
            quantity
            for score in scoring
            if isinstance(score, dict)
            for quantity in score.get("quantities", [])
        ][:12],
        "physics_list": physics.get("physics_list") if isinstance(physics, dict) else None,
    }


def _ids(items: Any, key: str) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item.get(key)) for item in items if isinstance(item, dict) and item.get(key)][:12]


def _model_unavailable(message: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "verdict": "unavailable",
        "usable": False,
        "warnings": [message],
        "rationale": message,
        "evidence": evidence or [],
    }


_MODEL_SYSTEM_PROMPT = """
Assess Gate 20 simulation output credibility. Return a JSON object with:
{"verdict":"supported|plausible|uncertain|unavailable|conflicting|invalid","rationale":"...","warnings":[]}
Use the deterministic artifact summary and model/task context only. No exact experiment match or
benchmark agreement is required. Mark conflicting only for internal contradictions or outputs that
cannot plausibly support the modeled simulation. Mark invalid only for unusable evidence.
""".strip()
