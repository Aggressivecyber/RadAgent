"""Runtime execution auditor for generated Geant4 projects."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from agent_core.gates.output_quality import (
    REQUIRED_G4_OUTPUTS,
    detect_smoke_runtime_errors,
    inspect_g4_output_quality,
)
from agent_core.models.gateway import _safe_parse_json, get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import GEANT4_PROJECT_DIRNAME, STAGE_CODEGEN

MAX_AUDIT_CONTEXT_CHARS = 45_000
RUNTIME_EXECUTION_AUDIT_PATH = f"{STAGE_CODEGEN}/runtime_execution_audit.json"

RUNTIME_AUDIT_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 runtime execution auditor。

你不写代码。你只判断这次 Geant4 工程是否真实完成了一次可用的 smoke simulation。
确定性事实优先：如果输入事实显示 build/run 失败、Geant4 batch command 失败、输出契约缺失、
artifact 写错目录、CSV schema 不对、数据明显是 fallback/固定假数据，你必须给出 fail 或 revise。
不要因为某个上游字段写了 success=true 就放行；必须解释证据链。

只返回 JSON，不要输出 Markdown fence。

返回格式：
{
  "status": "pass" | "revise" | "fail",
  "actually_ran": true,
  "artifact_contract_passed": true,
  "data_trustworthy": true,
  "findings": [{"severity": "low|medium|high", "target": "...", "message": "..."}],
  "required_fixes": [{"target": "...", "message": "..."}],
  "reviewer_notes": "..."
}
"""


async def run_runtime_execution_auditor(
    *,
    job_id: str,
    global_integration_report: dict[str, Any],
) -> dict[str, Any]:
    """Audit whether the latest Geant4 runtime gate actually ran valid output."""

    facts = collect_runtime_execution_facts(
        job_id=job_id,
        global_integration_report=global_integration_report,
    )
    llm_audit = await _run_lite_runtime_audit(job_id=job_id, facts=facts)

    deterministic_status = "fail" if facts["blocking_errors"] else "pass"
    llm_status = str(llm_audit.get("status", "pass")).lower()
    if deterministic_status == "fail":
        status = "fail"
    elif llm_status in {"fail", "revise"}:
        status = "revise"
    else:
        status = "pass"

    required_fixes = _merge_required_fixes(facts, llm_audit)
    audit = {
        "status": status,
        "deterministic_status": deterministic_status,
        "actually_ran": bool(facts.get("actually_ran")),
        "artifact_contract_passed": bool(facts.get("artifact_contract_passed")),
        "data_trustworthy": bool(facts.get("data_trustworthy")),
        "blocking_errors": list(facts["blocking_errors"]),
        "warnings": list(facts["warnings"]),
        "required_fixes": required_fixes,
        "facts": facts,
        "llm_audit": llm_audit,
        "evidence_path": RUNTIME_EXECUTION_AUDIT_PATH,
    }
    _persist_audit(audit, job_id)
    return audit


def runtime_audit_to_runtime_observation(audit: dict[str, Any]) -> dict[str, Any]:
    """Convert a failed runtime audit into an integration repair observation."""

    fixes = audit.get("required_fixes", [])
    errors = [
        f"{fix.get('target', 'runtime_execution')}: {fix.get('message', '')}"
        for fix in fixes
        if isinstance(fix, dict)
    ]
    if not errors:
        errors = [str(item) for item in audit.get("blocking_errors", [])]
    if not errors:
        errors = ["Runtime execution auditor rejected the simulation artifacts"]

    facts = audit.get("facts", {}) if isinstance(audit.get("facts"), dict) else {}
    artifacts = [
        {"path": path}
        for path in facts.get("artifact_paths", [])
        if isinstance(path, str) and path
    ]
    return {
        "status": "fail",
        "phase": "runtime_execution_audit",
        "project_dir": facts.get("project_dir"),
        "output_dir": facts.get("output_dir"),
        "errors": errors,
        "warnings": list(audit.get("warnings", [])),
        "artifacts": artifacts,
        "details": {
            "runtime_execution_audit": audit,
            "failed_gates": [
                {
                    "gate_id": "runtime_execution_audit",
                    "name": "Runtime execution authenticity audit",
                    "status": audit.get("status", "fail"),
                    "failed_items": errors,
                    "file_paths": [item["path"] for item in artifacts],
                    "message": (
                        "The latest Geant4 smoke run did not produce trustworthy "
                        "runtime artifacts."
                    ),
                }
            ],
        },
    }


def collect_runtime_execution_facts(
    *,
    job_id: str,
    global_integration_report: dict[str, Any],
) -> dict[str, Any]:
    """Collect deterministic runtime facts from the latest integration attempt."""

    latest_gate = _latest_runtime_gate(global_integration_report)
    attempt = latest_gate.get("attempt")
    attempt_dir = _attempt_dir(job_id, latest_gate, attempt)
    project_dir = _path_or_default(
        latest_gate.get("project_dir"),
        attempt_dir / GEANT4_PROJECT_DIRNAME,
    )
    output_dir = _path_or_default(
        latest_gate.get("output_dir"),
        attempt_dir / "g4_output_package",
    )

    if (attempt_dir / "runtime_gate_result.json").is_file():
        latest_gate = {
            **latest_gate,
            **_read_json(attempt_dir / "runtime_gate_result.json"),
        }

    smoke = _read_json(output_dir / "smoke_simulation_result.json")
    summary = _read_json(output_dir / "g4_summary.json")
    provenance = _read_json(output_dir / "provenance.json")
    expected_events = _positive_int(latest_gate.get("expected_events"))
    output_quality = inspect_g4_output_quality(output_dir, smoke_result=smoke)
    output_event_stats = _inspect_event_table(output_dir / "event_table.csv")
    build_event_stats = _inspect_event_table(project_dir / "build" / "event_table.csv")

    macro_events = _macro_beam_on_events(project_dir / "macros" / "run.mac")
    build_macro_events = _macro_beam_on_events(project_dir / "build" / "macros" / "run.mac")
    smoke_stderr = str(smoke.get("errors") or latest_gate.get("warnings") or "")
    runtime_error_patterns = _runtime_error_patterns(smoke, smoke_stderr)

    missing_outputs = [
        name for name in REQUIRED_G4_OUTPUTS if not (output_dir / name).is_file()
    ]
    misplaced_outputs = [
        name
        for name in REQUIRED_G4_OUTPUTS
        if not (output_dir / name).is_file() and (project_dir / "build" / name).is_file()
    ]

    blocking_errors: list[str] = []
    warnings: list[str] = []
    event_count_errors: list[str] = []

    if not latest_gate:
        blocking_errors.append("No runtime gate attempt was recorded")
    if global_integration_report.get("status") != "passed":
        blocking_errors.append(
            f"Global integration status is {global_integration_report.get('status', 'missing')}"
        )
    if latest_gate.get("status") and latest_gate.get("status") != "pass":
        blocking_errors.append(f"Runtime gate status is {latest_gate.get('status')}")
    if latest_gate.get("cmake_configure_result", {}).get("success") is False:
        blocking_errors.append("CMake configure failed")
    if latest_gate.get("build_result", {}).get("success") is False:
        blocking_errors.append("Geant4 build failed")
    if smoke and smoke.get("success") is not True:
        blocking_errors.append("Smoke simulation success flag is false")
    if smoke and smoke.get("process_success") is False:
        blocking_errors.append("Smoke simulation process returned failure")
    if runtime_error_patterns:
        blocking_errors.append(
            "Smoke simulation stderr contains Geant4 runtime errors: "
            + ", ".join(runtime_error_patterns)
        )
    if missing_outputs:
        blocking_errors.append(
            "Missing output contract files in G4_OUTPUT_DIR: " + ", ".join(missing_outputs)
        )
    if misplaced_outputs:
        blocking_errors.append(
            "Output contract files were written under build/ instead of G4_OUTPUT_DIR: "
            + ", ".join(misplaced_outputs)
        )
    blocking_errors.extend(output_quality.errors)
    blocking_errors.extend(output_event_stats["errors"])
    if build_event_stats["exists"]:
        warnings.extend(
            "build/event_table.csv: " + item for item in build_event_stats["warnings"]
        )
        blocking_errors.extend(
            "build/event_table.csv: " + item for item in build_event_stats["errors"]
        )

    events_requested = _positive_int(summary.get("events_requested"))
    if expected_events is not None:
        if macro_events is not None and macro_events != expected_events:
            event_count_errors.append(
                f"run.mac requests {macro_events} events; expected {expected_events} events"
            )
        if events_requested is not None and events_requested != expected_events:
            event_count_errors.append(
                "g4_summary.json records "
                f"{events_requested} events; expected {expected_events} events"
            )
        if output_event_stats["row_count"] and output_event_stats["row_count"] != expected_events:
            event_count_errors.append(
                "event_table.csv row count is "
                f"{output_event_stats['row_count']}; expected {expected_events} events"
            )
        if events_requested is None:
            event_count_errors.append(
                f"g4_summary.json missing events_requested; expected {expected_events} events"
            )
        if macro_events is None:
            event_count_errors.append(
                f"run.mac missing /run/beamOn; expected {expected_events} events"
            )
    blocking_errors.extend(event_count_errors)
    if macro_events and events_requested and macro_events != events_requested:
        blocking_errors.append(
            f"run.mac requests {macro_events} events but g4_summary.json records {events_requested}"
        )
    if macro_events and output_event_stats["row_count"]:
        if output_event_stats["row_count"] != macro_events:
            blocking_errors.append(
                "event_table.csv row count does not match /run/beamOn "
                f"({output_event_stats['row_count']} vs {macro_events})"
            )
    if build_macro_events and build_macro_events != macro_events:
        warnings.append(
            "build/macros/run.mac beamOn "
            f"{build_macro_events} differs from source macro {macro_events}"
        )
    if summary.get("materialized_by_runner") is True:
        blocking_errors.append(
            "g4_summary.json was materialized by Geant4Runner, not the generated program"
        )
    if provenance.get("materialized_by_runner") is True:
        blocking_errors.append(
            "provenance.json was materialized by Geant4Runner, not the generated program"
        )

    artifact_contract_passed = not missing_outputs and not output_quality.errors
    actually_ran = (
        bool(smoke)
        and smoke.get("success") is True
        and not runtime_error_patterns
        and latest_gate.get("build_result", {}).get("success") is not False
    )
    data_trustworthy = (
        artifact_contract_passed
        and not output_event_stats["errors"]
        and not build_event_stats["errors"]
        and not misplaced_outputs
        and not event_count_errors
    )

    artifact_paths = [
        str(path)
        for path in (
            attempt_dir / "runtime_gate_result.json",
            output_dir / "smoke_simulation_result.json",
            output_dir / "g4_summary.json",
            output_dir / "event_table.csv",
            output_dir / "edep_3d.csv",
            output_dir / "dose_3d.csv",
            output_dir / "provenance.json",
            project_dir / "macros" / "run.mac",
            project_dir / "build" / "event_table.csv",
        )
        if path.is_file()
    ]

    return {
        "job_id": job_id,
        "attempt": attempt,
        "attempt_dir": str(attempt_dir),
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "global_integration_status": global_integration_report.get("status"),
        "runtime_gate_status": latest_gate.get("status"),
        "actually_ran": actually_ran,
        "artifact_contract_passed": artifact_contract_passed,
        "data_trustworthy": data_trustworthy,
        "missing_outputs": missing_outputs,
        "misplaced_outputs": misplaced_outputs,
        "runtime_error_patterns": runtime_error_patterns,
        "macro_beam_on_events": macro_events,
        "build_macro_beam_on_events": build_macro_events,
        "expected_events": expected_events,
        "events_requested": events_requested,
        "smoke_result": _trim_json_value(smoke, max_chars=8_000),
        "g4_summary": _trim_json_value(summary, max_chars=4_000),
        "provenance": _trim_json_value(provenance, max_chars=4_000),
        "output_quality": {
            "status": "pass" if not output_quality.errors else "fail",
            "errors": output_quality.errors,
            "warnings": output_quality.warnings,
            "metrics": output_quality.metrics,
        },
        "event_table": output_event_stats,
        "build_event_table": build_event_stats,
        "blocking_errors": _dedupe(blocking_errors),
        "warnings": _dedupe(warnings + output_quality.warnings),
        "artifact_paths": artifact_paths,
    }


async def _run_lite_runtime_audit(*, job_id: str, facts: dict[str, Any]) -> dict[str, Any]:
    context = {
        "job_id": job_id,
        "runtime_execution_facts": _trim_json_value(facts, max_chars=40_000),
        "instruction": (
            "Classify whether the latest Geant4 smoke simulation actually ran and "
            "whether artifacts are trustworthy. You may tighten deterministic findings "
            "but must not ignore blocking_errors."
        ),
    }
    prompt = json.dumps(context, indent=2, ensure_ascii=False)
    if len(prompt) > MAX_AUDIT_CONTEXT_CHARS:
        prompt = prompt[: MAX_AUDIT_CONTEXT_CHARS - 36] + "\n[truncated audit context]"

    gateway = get_model_gateway()
    result = await gateway.call(
        task=ModelTask.CONTEXT_SUMMARY,
        tier=ModelTier.LITE,
        system_prompt=RUNTIME_AUDIT_SYSTEM_PROMPT,
        user_prompt=prompt,
        response_format="json",
        max_tokens=3072,
        metadata={
            "job_id": job_id,
            "module_name": "runtime_execution_auditor",
            "enable_thinking": False,
        },
    )
    model_info = {
        "model_name": result.model_name,
        "tier": str(result.tier),
        "latency_ms": result.latency_ms,
        "error": result.error,
    }
    if result.error:
        return {
            "status": "revise",
            "actually_ran": facts.get("actually_ran", False),
            "artifact_contract_passed": facts.get("artifact_contract_passed", False),
            "data_trustworthy": facts.get("data_trustworthy", False),
            "findings": [
                {
                    "severity": "medium",
                    "target": "runtime_execution_auditor",
                    "message": f"LITE audit model call failed: {result.error}",
                }
            ],
            "required_fixes": [],
            "reviewer_notes": "Deterministic runtime facts were still used.",
            "summary_model": model_info,
        }

    data = result.parsed_json or _safe_parse_json(result.content) or {}
    audit = _normalize_llm_audit(data)
    audit["summary_model"] = model_info
    return audit


def _normalize_llm_audit(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    status = str(data.get("status", "fail")).strip().lower()
    if status not in {"pass", "revise", "fail"}:
        status = "fail"
    return {
        "status": status,
        "actually_ran": bool(data.get("actually_ran")),
        "artifact_contract_passed": bool(data.get("artifact_contract_passed")),
        "data_trustworthy": bool(data.get("data_trustworthy")),
        "findings": _list_of_dicts(data.get("findings", [])),
        "required_fixes": _list_of_dicts(data.get("required_fixes", [])),
        "reviewer_notes": str(data.get("reviewer_notes", "")),
    }


def _merge_required_fixes(
    facts: dict[str, Any],
    llm_audit: dict[str, Any],
) -> list[dict[str, str]]:
    fixes: list[dict[str, str]] = []
    for error in facts.get("blocking_errors", []):
        fixes.append({"target": "runtime_execution", "message": str(error)})
    for fix in llm_audit.get("required_fixes", []):
        if isinstance(fix, dict) and fix.get("message"):
            fixes.append(
                {
                    "target": str(fix.get("target", "runtime_execution")),
                    "message": str(fix.get("message", "")),
                }
            )
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for fix in fixes:
        key = (fix["target"], fix["message"])
        if key not in seen:
            seen.add(key)
            deduped.append(fix)
    return deduped


def _latest_runtime_gate(report: dict[str, Any]) -> dict[str, Any]:
    attempts = report.get("runtime_gate_attempts", [])
    if isinstance(attempts, list) and attempts:
        dict_attempts = [item for item in attempts if isinstance(item, dict)]
        if dict_attempts:
            return max(dict_attempts, key=lambda item: _positive_int(item.get("attempt")) or -1)
    final_gate = report.get("final_runtime_gate")
    return final_gate if isinstance(final_gate, dict) else {}


def _attempt_dir(job_id: str, gate: dict[str, Any], attempt: Any) -> Path:
    project_dir = gate.get("project_dir")
    if project_dir:
        path = Path(str(project_dir))
        if path.name == GEANT4_PROJECT_DIRNAME:
            return path.parent
    output_dir = gate.get("output_dir")
    if output_dir:
        path = Path(str(output_dir))
        if path.name == "g4_output_package":
            return path.parent
    attempt_id = _positive_int(attempt) or 0
    return get_job_dir(job_id) / STAGE_CODEGEN / "integration" / f"runtime_attempt_{attempt_id}"


def _path_or_default(value: Any, default: Path) -> Path:
    if value:
        return Path(str(value))
    return default


def _runtime_error_patterns(smoke: dict[str, Any], stderr: str) -> list[str]:
    patterns = [str(item) for item in smoke.get("runtime_error_patterns", []) if item]
    patterns.extend(detect_smoke_runtime_errors(stderr))
    return _dedupe(patterns)


def _macro_beam_on_events(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    matches = re.findall(r"^\s*/run/beamOn\s+(\d+)\b", text, flags=re.MULTILINE)
    if not matches:
        return None
    return _positive_int(matches[-1])


def _inspect_event_table(path: Path) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "fieldnames": [],
        "row_count": 0,
        "numeric_columns": {},
        "errors": [],
        "warnings": [],
    }
    if not path.is_file():
        return stats
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
    except OSError as exc:
        stats["errors"].append(f"event table unreadable: {exc}")
        return stats

    stats["fieldnames"] = fieldnames
    stats["row_count"] = len(rows)
    required = {"EventID", "edep_MeV", "dose_Gy"}
    missing = sorted(required - set(fieldnames))
    if missing:
        stats["errors"].append("missing required columns: " + ", ".join(missing))
    if not rows:
        stats["errors"].append("has no event rows")
        return stats

    for column in fieldnames:
        values: list[float] = []
        invalid_count = 0
        for row in rows:
            try:
                values.append(float(row.get(column, "")))
            except (TypeError, ValueError):
                invalid_count += 1
        if invalid_count:
            stats["warnings"].append(
                f"column {column} has {invalid_count} non-numeric value(s)"
            )
        if not values:
            continue
        unique_values = sorted(set(values))
        stats["numeric_columns"][column] = {
            "count": len(values),
            "unique_count": len(unique_values),
            "min": min(values),
            "max": max(values),
        }
        if (
            len(rows) >= 10
            and len(unique_values) == 1
            and column.lower() not in {"eventid", "event_id"}
        ):
            stats["errors"].append(
                f"column {column} has one identical value across {len(rows)} rows"
            )
    return stats


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _trim_json_value(value: Any, *, max_chars: int) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return value
    return {"summary": text[: max_chars - 32] + "\n[truncated for audit]"}


def _persist_audit(audit: dict[str, Any], job_id: str) -> None:
    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)
    (codegen_dir / "runtime_execution_audit.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
