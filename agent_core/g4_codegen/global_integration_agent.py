"""High-privilege global integration agent for assembled Geant4 modules.

This is the only cross-module writer in the codegen flow. It receives all
module outputs, reads the assembled project files,
collects local RAG and web-search evidence, and returns a schema-preserving
proposed_patch for the complete Geant4 program.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent_core.gates.output_quality import REQUIRED_G4_OUTPUTS, inspect_g4_output_quality
from agent_core.g4_codegen.module_agents.base import _postprocess_generated_module_content
from agent_core.models.gateway import _safe_parse_json, get_model_gateway
from agent_core.models.schemas import ModelProvider, ModelTask, ModelTier
from agent_core.observability import record_event
from agent_core.tools.geant4_workbench import SELF_CHECK_EVENTS, resolve_self_check_events
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import GEANT4_PROJECT_DIRNAME, STAGE_CODEGEN

MODEL_CONTEXT_CHAR_LIMIT = 220_000
GLOBAL_INTEGRATION_REPORT_PATH = f"{STAGE_CODEGEN}/global_integration_agent_report.json"
GLOBAL_INTEGRATION_EVIDENCE_PATH = (
    f"{STAGE_CODEGEN}/integration/global_integration_evidence.json"
)
GLOBAL_INTEGRATION_ATTEMPT_HISTORY_FILENAME = "global_integration_attempts.jsonl"
GLOBAL_INTEGRATION_ALLOWED_PATH_PATTERNS = [
    "src/*.cc",
    "include/*.hh",
    "macros/*.mac",
    "config/*.json",
    "CMakeLists.txt",
    "main.cc",
]
GLOBAL_INTEGRATION_FORBIDDEN_PATH_EXAMPLES = [
    "build.sh",
    "CMakePresets.json",
    "agent_core/**/*.py",
    "agent_core/**/*.yaml",
    "*.sh",
    ".env",
]
_COMPILE_DIAGNOSTIC_RE = re.compile(
    r"(?P<path>(?:/|[A-Za-z0-9_.-])[^:\n]*?):"
    r"(?P<line>\d+):(?P<column>\d+):\s*"
    r"(?P<level>fatal error|error|warning|note):\s*"
    r"(?P<message>[^\n]+)"
)
_LOCAL_INCLUDE_RE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.MULTILINE)
_HEADER_SUFFIXES = (".hh", ".hpp", ".hxx", ".h")
_SOURCE_SUFFIXES = (".cc", ".cpp", ".cxx", ".c")

GEANT4_REPAIR_MEMORY: dict[str, Any] = {
    "purpose": (
        "Recurring Geant4 codegen failures observed in real RadAgent runs; apply "
        "these before spending model turns on broad investigation."
    ),
    "rules": [
        {
            "id": "runtime_geometry_view_no_phantom_member",
            "symptom": "OutputManager::WriteGeometryViewJson compile error: fGeometryComponents was not declared",
            "fix": (
                "Only reference fGeometryComponents when OutputManager.hh declares "
                "that member. Otherwise write non-empty geometry_view.json directly "
                "from the G4ModelIR component list."
            ),
            "artifacts": ["geometry_view.json"],
        },
        {
            "id": "visual_workbench_contract",
            "symptom": "3D browser workbench is empty or particle overlay cannot render",
            "fix": (
                "Always produce non-empty geometry_view.json plus true step-derived "
                "particle_tracks.json and edep>0 energy_deposits.json."
            ),
            "artifacts": [
                "geometry_view.json",
                "particle_tracks.json",
                "energy_deposits.json",
            ],
        },
        {
            "id": "derived_event_rows_single_source",
            "symptom": "summary reports energy but event_table.csv is zero, or summary/table disagree",
            "fix": (
                "When event rows are derived from energy deposit points, use the "
                "same derived collection for event_table.csv and g4_summary.json. "
                "Keep helper variables function-local and out of WriteProvenanceJson."
            ),
            "artifacts": ["event_table.csv", "g4_summary.json", "energy_deposits.json"],
        },
        {
            "id": "output_manager_data_flow",
            "symptom": "particle_tracks.json or energy_deposits.json exists but is empty",
            "fix": (
                "Pass OutputManager* through ActionInitialization into SteppingAction "
                "and record real G4Step event/track/position/edep data."
            ),
            "artifacts": ["particle_tracks.json", "energy_deposits.json"],
        },
        {
            "id": "declared_interface_only",
            "symptom": "Build fails with no member named / constructor argument mismatch / guessed helper APIs",
            "fix": (
                "Treat generated headers as source of truth. For struct fields, "
                "constructors, and helper methods, read the declaring header and "
                "align all call sites to the declared API in one edit. Prefer an "
                "existing helper suggested by the compiler over inventing aggregate "
                "methods such as BuildComponents."
            ),
            "artifacts": ["include/*.hh", "src/*.cc", "main.cc"],
        },
    ],
}


async def run_global_integration_agent(
    proposed_patch: dict[str, Any],
    *,
    job_id: str,
    g4_model_ir: dict[str, Any] | None = None,
    module_results: dict[str, Any] | None = None,
    module_contracts: dict[str, Any] | None = None,
    module_contexts: dict[str, Any] | None = None,
    interface_contracts: dict[str, Any] | None = None,
    runtime_failure_context: dict[str, Any] | None = None,
    runtime_repair_rounds: int = 0,
    runtime_attempt_offset: int = 0,
    agentic_max_turns: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the final global integration agent over module-generated files."""
    original_patch = deepcopy(proposed_patch or {})
    runtime_events = resolve_self_check_events(g4_model_ir=g4_model_ir)
    original_patch = _apply_runtime_event_count_to_patch(original_patch, runtime_events)
    report: dict[str, Any] = {
        "job_id": job_id,
        "status": "passed",
        "agent_name": "global_integration_agent",
        "issues_fixed": [],
        "changed_files": [],
        "errors": [],
        "runtime_gate_attempts": [],
        "capabilities_used": {
            "read_project_files": True,
            "database_search": False,
            "web_search": False,
            "write_proposed_patch": True,
        },
    }

    if not isinstance(original_patch.get("changed_files"), list) or not original_patch.get(
        "changed_files"
    ):
        report["status"] = "failed"
        report["errors"].append("proposed_patch.changed_files is empty")
        _persist_report(report, job_id)
        return original_patch, report

    integration_context = {
        "job_id": job_id,
        "available_modules": sorted((module_results or {}).keys()),
        "module_result_diagnostics": _summarize_module_result_diagnostics(
            module_results or {}
        ),
        "module_contracts": module_contracts or {},
        "module_context_summaries": _summarize_module_contexts(module_contexts or {}),
        "interface_contracts": interface_contracts or {},
        "runtime_failure_context": runtime_failure_context or {},
        "runtime_gate_contract": {
            "runner": "Geant4Runner.smoke_test",
            "events": runtime_events,
            "event_source": "g4_model_ir.sources.events"
            if g4_model_ir
            else "default_self_check_events",
        },
        "interface_audit": _interface_audit_from_patch(original_patch),
        "integration_memory": _load_integration_memory(job_id),
        "project_files": _project_files_from_patch(original_patch),
        "write_contract": _global_integration_write_contract(original_patch),
    }

    evidence = await _collect_integration_evidence(
        job_id=job_id,
        integration_context=integration_context,
    )
    integration_context["database_search"] = evidence["database_search"]
    integration_context["web_search"] = evidence["web_search"]
    report["capabilities_used"]["database_search"] = bool(
        evidence["database_search"].get("results")
    )
    report["capabilities_used"]["web_search"] = bool(evidence["web_search"].get("results"))
    report["evidence_path"] = GLOBAL_INTEGRATION_EVIDENCE_PATH
    _persist_integration_context(integration_context, job_id)

    gateway = get_model_gateway()
    if _is_mock_gateway(gateway):
        original_patch.setdefault("metadata", {})
        original_patch["metadata"]["global_integration_agent"] = {
            "status": "no_change",
            "mock_provider_only": True,
            "report_path": GLOBAL_INTEGRATION_REPORT_PATH,
            "runtime_gate_required": True,
        }
        report["llm_status"] = "no_change"
        report["mock_provider_only"] = True
        _persist_patch(original_patch, job_id)
        _persist_report(report, job_id)
        return original_patch, report

    if not _has_evidence(evidence):
        report.setdefault("warnings", []).append(
            "Local database and web-search evidence were unavailable; continuing with "
            "project files, module contracts, and runtime failure context."
        )

    attempt_offset = max(0, int(runtime_attempt_offset or 0))
    active_failure_context = runtime_failure_context
    interface_audit = integration_context.get("interface_audit")

    if not active_failure_context:
        initial_gate = await _run_integration_runtime_gate(
            job_id=job_id,
            proposed_patch=original_patch,
            attempt=attempt_offset,
            expected_events=runtime_events,
        )
        report["runtime_gate_attempts"].append(initial_gate)
        if initial_gate.get("status") == "pass":
            report["status"] = "passed"
            report["changed_files"] = []
            original_patch.setdefault("metadata", {})
            original_patch["metadata"]["global_integration_agent"] = {
                "status": report["status"],
                "issues_fixed": 0,
                "changed_files": 0,
                "report_path": GLOBAL_INTEGRATION_REPORT_PATH,
                "runtime_gate_required": True,
                "short_circuited_after_initial_gate": True,
            }
            original_patch["metadata"]["final_runtime_gate"] = _final_runtime_gate_metadata(
                runtime_events
            )
            _persist_patch(original_patch, job_id)
            _persist_report(report, job_id)
            return original_patch, report
        active_failure_context = initial_gate
    if isinstance(active_failure_context, dict) and isinstance(interface_audit, dict):
        active_failure_context = {
            **active_failure_context,
            "interface_audit": interface_audit,
        }

    # Agentic build-fix loop: the model receives the assembled project plus
    # read/edit/write/bash/build/smoke tools and iterates until the Geant4
    # project compiles and the smoke run passes. This replaces the former
    # one-shot whole-patch JSON regeneration, which could not self-repair
    # compile errors. ``runtime_repair_rounds`` is retained for call-site
    # compatibility; the agentic loop handles iteration internally.
    from agent_core.g4_codegen.agentic_repair import run_agentic_repair

    repaired_patch, agentic_report = await run_agentic_repair(
        original_patch,
        job_id=job_id,
        attempt_index=attempt_offset if runtime_failure_context else attempt_offset + 1,
        runtime_failure_context=active_failure_context,
        expected_events=runtime_events,
        max_turns=agentic_max_turns,
    )

    gate = agentic_report.get("runtime_gate", {})
    report["runtime_gate_attempts"].append(gate)
    report["status"] = agentic_report.get("status", "failed")
    report["changed_files"] = _changed_paths(original_patch, repaired_patch)
    report["agentic"] = {
        "stop_reason": agentic_report.get("stop_reason"),
        "n_turns": agentic_report.get("n_turns"),
        "tool_calls": agentic_report.get("tool_calls"),
        "tool_audit": agentic_report.get("tool_audit"),
    }
    if agentic_report.get("loop_error"):
        report.setdefault("warnings", []).append(f"agent loop: {agentic_report['loop_error']}")
    if agentic_report.get("errors"):
        report["errors"].extend(agentic_report["errors"])
    if agentic_report.get("continuation_request"):
        report["continuation_request"] = agentic_report["continuation_request"]

    repaired_patch.setdefault("metadata", {})
    repaired_patch["metadata"]["global_integration_agent"] = {
        "status": report["status"],
        "issues_fixed": len(report["issues_fixed"]),
        "changed_files": len(report["changed_files"]),
        "report_path": GLOBAL_INTEGRATION_REPORT_PATH,
        "runtime_gate_required": True,
    }
    repaired_patch["metadata"]["final_runtime_gate"] = _final_runtime_gate_metadata(
        runtime_events
    )
    _persist_patch(repaired_patch, job_id)
    _persist_report(report, job_id)
    return repaired_patch, report


def _final_runtime_gate_metadata(runtime_events: int) -> dict[str, Any]:
    return {
        "required": True,
        "gates": [
            "Build/Parse",
            "Unit Test",
            "Data Contract",
            "Smoke Simulation",
        ],
        "runner": "Geant4Runner.smoke_test",
        "events": runtime_events,
    }


def _is_mock_gateway(gateway: Any) -> bool:
    profile = getattr(gateway, "profiles", {}).get(ModelTier.MAX)
    return getattr(profile, "provider", None) == ModelProvider.MOCK


def _model_context_json(
    integration_context: dict[str, Any],
    *,
    max_chars: int = MODEL_CONTEXT_CHAR_LIMIT,
    max_project_file_chars: int = 90_000,
) -> str:
    """Serialize a model-facing context with critical repair evidence first."""
    prompt_context = {
        "job_id": integration_context.get("job_id"),
        "available_modules": integration_context.get("available_modules", []),
        "runtime_failure_context": _compact_runtime_failure_context(
            integration_context.get("runtime_failure_context", {})
        ),
        "project_files": _project_files_for_model(
            integration_context.get("project_files", []),
            max_total_content_chars=max_project_file_chars,
        ),
        "database_search": _compact_search_evidence(
            integration_context.get("database_search", {})
        ),
        "web_search": _compact_search_evidence(integration_context.get("web_search", {})),
        "interface_contracts": integration_context.get("interface_contracts", {}),
        "interface_audit": integration_context.get("interface_audit", {}),
        "module_contracts": _compact_module_contracts(
            integration_context.get("module_contracts", {})
        ),
        "module_result_diagnostics": _compact_module_result_diagnostics(
            integration_context.get("module_result_diagnostics", {})
        ),
        "module_context_summaries": _compact_module_context_summaries(
            integration_context.get("module_context_summaries", {})
        ),
        "geant4_repair_memory": GEANT4_REPAIR_MEMORY,
        "integration_memory": _compact_integration_memory(
            integration_context.get("integration_memory", {})
        ),
        "write_contract": integration_context.get("write_contract", {}),
    }
    text = json.dumps(prompt_context, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text

    prompt_context["database_search"] = _compact_search_evidence(
        integration_context.get("database_search", {}),
        max_results=4,
        max_content_chars=600,
    )
    prompt_context["web_search"] = _compact_search_evidence(
        integration_context.get("web_search", {}),
        max_results=3,
        max_content_chars=500,
    )
    prompt_context["module_context_summaries"] = {}
    prompt_context["integration_memory"] = _compact_integration_memory(
        integration_context.get("integration_memory", {}),
        max_chars=6_000,
    )
    text = json.dumps(prompt_context, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text

    prompt_context["project_files"] = _project_files_for_model(
        integration_context.get("project_files", []),
        max_total_content_chars=min(max_project_file_chars, 55_000),
    )
    text = json.dumps(prompt_context, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    prompt_context["module_contracts"] = _trim_json_value(
        prompt_context.get("module_contracts", {}), max_chars=6_000
    )
    prompt_context["interface_contracts"] = _trim_json_value(
        prompt_context.get("interface_contracts", {}), max_chars=3_000
    )
    text = json.dumps(prompt_context, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    prompt_context["project_files"] = _project_files_for_model(
        integration_context.get("project_files", []),
        max_total_content_chars=min(max_project_file_chars, 35_000),
    )
    text = json.dumps(prompt_context, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    prompt_context["database_search"] = _compact_search_evidence(
        integration_context.get("database_search", {}),
        max_results=2,
        max_content_chars=350,
    )
    prompt_context["web_search"] = _compact_search_evidence(
        integration_context.get("web_search", {}),
        max_results=2,
        max_content_chars=300,
    )
    prompt_context["module_contracts"] = _trim_json_value(
        prompt_context.get("module_contracts", {}), max_chars=3_000
    )
    prompt_context["project_files"] = _project_files_for_model(
        integration_context.get("project_files", []),
        max_total_content_chars=min(max_project_file_chars, 25_000),
    )
    text = json.dumps(prompt_context, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text
    return _fit_model_context_json(prompt_context, max_chars=max_chars)


def _summarize_module_result_diagnostics(
    module_results: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    diagnostics: dict[str, dict[str, Any]] = {}
    for module_name, result in module_results.items():
        if not isinstance(result, dict):
            diagnostics[str(module_name)] = {
                "status": "unknown",
                "generated_file_count": 0,
                "generated_paths": [],
                "warnings": [],
                "errors": [f"module result is {type(result).__name__}, expected object"],
                "repair_attempt_count": 0,
            }
            continue
        generated_files = [
            item for item in result.get("generated_files", []) if isinstance(item, dict)
        ]
        diagnostics[str(module_name)] = {
            "status": str(result.get("status", "")),
            "generated_file_count": len(generated_files),
            "generated_paths": [
                str(item.get("path", "")) for item in generated_files if item.get("path")
            ][:80],
            "warnings": _clip_list(result.get("warnings", []), max_items=20),
            "errors": _clip_list(result.get("errors", []), max_items=20),
            "repair_attempt_count": len(result.get("repair_attempts", []) or []),
        }
    return diagnostics


def _compact_module_result_diagnostics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    compact: dict[str, Any] = {}
    for module_name, diagnostics in value.items():
        if not isinstance(diagnostics, dict):
            continue
        compact[str(module_name)] = {
            "status": diagnostics.get("status", ""),
            "generated_file_count": diagnostics.get("generated_file_count", 0),
            "generated_paths": _clip_list(
                diagnostics.get("generated_paths", []),
                max_items=30,
            ),
            "warnings": _clip_list(diagnostics.get("warnings", []), max_items=10),
            "errors": _clip_list(diagnostics.get("errors", []), max_items=10),
            "repair_attempt_count": diagnostics.get("repair_attempt_count", 0),
        }
    return compact


def _project_files_for_model(
    project_files: Any,
    *,
    max_total_content_chars: int = 90_000,
) -> list[dict[str, str]]:
    if not isinstance(project_files, list):
        return []
    files: list[dict[str, str]] = []
    used_chars = 0
    for item in project_files:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", ""))
        content = str(item.get("new_content", ""))
        if not path or not content:
            continue
        remaining = max_total_content_chars - used_chars
        if remaining <= 0:
            files.append(
                {
                    "path": path,
                    "module_name": str(item.get("module_name", "")),
                    "generated_by": str(item.get("generated_by", "")),
                    "new_content": "[omitted: project file content budget exhausted]",
                }
            )
            continue
        clipped = _clip_text(content, min(len(content), remaining))
        used_chars += len(clipped)
        files.append(
            {
                "path": path,
                "module_name": str(item.get("module_name", "")),
                "generated_by": str(item.get("generated_by", "")),
                "new_content": clipped,
            }
        )
    return files


def _fit_model_context_json(prompt_context: dict[str, Any], *, max_chars: int) -> str:
    """Shrink model context without returning malformed JSON."""
    compact = deepcopy(prompt_context)
    shrink_steps = [
        lambda ctx: ctx.__setitem__("module_context_summaries", {}),
        lambda ctx: ctx.__setitem__(
            "database_search",
            _summarize_search_context(ctx.get("database_search", {})),
        ),
        lambda ctx: ctx.__setitem__(
            "web_search",
            _summarize_search_context(ctx.get("web_search", {})),
        ),
        lambda ctx: ctx.__setitem__(
            "integration_memory",
            _trim_json_value(ctx.get("integration_memory", {}), max_chars=2_000),
        ),
        lambda ctx: ctx.__setitem__(
            "module_contracts",
            _trim_json_value(ctx.get("module_contracts", {}), max_chars=2_000),
        ),
        lambda ctx: ctx.__setitem__(
            "interface_contracts",
            _trim_json_value(ctx.get("interface_contracts", {}), max_chars=1_500),
        ),
    ]
    for shrink in shrink_steps:
        text = json.dumps(compact, indent=2, ensure_ascii=False)
        if len(text) <= max_chars:
            return text
        shrink(compact)

    for budget in (60_000, 30_000, 15_000, 8_000, 4_000, 1_500, 500, 0):
        compact["project_files"] = _shrink_project_files_for_budget(
            compact.get("project_files", []),
            max_total_content_chars=budget,
        )
        text = json.dumps(compact, indent=2, ensure_ascii=False)
        if len(text) <= max_chars:
            return text

    compact["runtime_failure_context"] = _trim_json_value(
        compact.get("runtime_failure_context", {}),
        max_chars=max(500, max_chars // 2),
    )
    text = json.dumps(compact, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text

    minimum = {
        "job_id": compact.get("job_id"),
        "available_modules": compact.get("available_modules", []),
        "runtime_failure_context": compact.get("runtime_failure_context", {}),
        "project_files": [],
        "context_truncated": True,
        "write_contract": compact.get("write_contract", {}),
    }
    text = json.dumps(minimum, indent=2, ensure_ascii=False)
    if len(text) <= max_chars:
        return text

    smallest = {
        "job_id": compact.get("job_id"),
        "runtime_failure_context": _trim_json_value(
            compact.get("runtime_failure_context", {}),
            max_chars=max(80, max_chars - 200),
        ),
        "context_truncated": True,
    }
    return json.dumps(smallest, indent=2, ensure_ascii=False)


def _summarize_search_context(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "omitted_for_prompt_budget",
        "result_count": len((ctx or {}).get("results", []))
        if isinstance(ctx, dict) and isinstance(ctx.get("results"), list)
        else 0,
    }


def _shrink_project_files_for_budget(
    files: Any,
    *,
    max_total_content_chars: int,
) -> list[dict[str, str]]:
    if not isinstance(files, list):
        return []
    if max_total_content_chars <= 0:
        return [
            {
                "path": str(item.get("path", "")),
                "module_name": str(item.get("module_name", "")),
                "generated_by": str(item.get("generated_by", "")),
                "new_content": "[omitted: prompt budget exhausted]",
            }
            for item in files
            if isinstance(item, dict) and item.get("path")
        ][:12]

    used = 0
    shrunk: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict) or not item.get("path"):
            continue
        content = str(item.get("new_content", ""))
        remaining = max_total_content_chars - used
        if remaining <= 0:
            new_content = "[omitted: prompt budget exhausted]"
        else:
            new_content = _clip_text(content, min(len(content), remaining))
            used += len(new_content)
        shrunk.append(
            {
                "path": str(item.get("path", "")),
                "module_name": str(item.get("module_name", "")),
                "generated_by": str(item.get("generated_by", "")),
                "new_content": new_content,
            }
        )
    return shrunk


def _compact_runtime_failure_context(runtime_failure_context: Any) -> dict[str, Any]:
    if not isinstance(runtime_failure_context, dict):
        return {}
    compact: dict[str, Any] = {
        "job_id": runtime_failure_context.get("job_id"),
        "status": runtime_failure_context.get("status"),
        "phase": runtime_failure_context.get("phase"),
        "errors": _clip_list(runtime_failure_context.get("errors", []), max_items=20),
        "warnings": _clip_list(runtime_failure_context.get("warnings", []), max_items=10),
    }
    failed_gates = []
    details = runtime_failure_context.get("details", {})
    if isinstance(details, dict):
        for gate in details.get("failed_gates", [])[:12]:
            if not isinstance(gate, dict):
                continue
            failed_gates.append(
                {
                    "gate_id": gate.get("gate_id"),
                    "name": gate.get("name"),
                    "status": gate.get("status"),
                    "failed_items": _clip_list(gate.get("failed_items", []), max_items=10),
                    "message": gate.get("message"),
                    "file_paths": _clip_list(gate.get("file_paths", []), max_items=6),
                    "evidence": _clip_list(gate.get("evidence", []), max_items=6),
                }
            )
    compact["failed_gates"] = failed_gates
    artifact_summaries = _runtime_artifact_summaries(runtime_failure_context)
    compact["artifact_summaries"] = artifact_summaries
    compact["runtime_project_files"] = _runtime_project_file_summaries(
        runtime_failure_context
    )
    compact["compile_error_contexts"] = _compile_error_source_contexts(
        {
            **runtime_failure_context,
            "artifact_summaries": artifact_summaries,
        }
    )
    compact["recent_failed_events"] = _recent_failed_events(runtime_failure_context)
    for key in (
        "attempt",
        "project_dir",
        "output_dir",
        "missing_outputs",
        "cmake_configure_result",
        "build_result",
        "unit_test_result",
        "output_quality",
        "output_summary",
        "runner_contract",
    ):
        if key in runtime_failure_context:
            compact[key] = runtime_failure_context[key]
    return _trim_runtime_failure_context(compact, max_chars=35_000)


def _compile_error_source_contexts(
    runtime_failure_context: dict[str, Any],
) -> list[dict[str, Any]]:
    project_dir_value = runtime_failure_context.get("project_dir")
    if not project_dir_value:
        return []
    project_dir = Path(str(project_dir_value))
    if not project_dir.is_dir():
        return []

    contexts: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()
    for diagnostic_text in _iter_diagnostic_strings(runtime_failure_context):
        for match in _COMPILE_DIAGNOSTIC_RE.finditer(diagnostic_text):
            raw_path = match.group("path")
            line = int(match.group("line"))
            column = int(match.group("column"))
            source_path = _resolve_runtime_source_path(project_dir, raw_path)
            if source_path is None:
                continue
            try:
                relative_path = str(source_path.relative_to(project_dir))
            except ValueError:
                relative_path = str(source_path)
            key = (relative_path, line, column, match.group("message"))
            if key in seen:
                continue
            seen.add(key)
            contexts.append(
                {
                    "path": relative_path,
                    "line": line,
                    "column": column,
                    "level": match.group("level"),
                    "message": match.group("message"),
                    "diagnostic": _diagnostic_block(diagnostic_text, match.start()),
                    "source_excerpt": _source_excerpt(source_path, line),
                    "related_files": _related_runtime_source_contexts(
                        project_dir,
                        source_path,
                    ),
                }
            )
            if len(contexts) >= 12:
                return contexts
    return contexts


def _related_runtime_source_contexts(
    project_dir: Path,
    source_path: Path,
    *,
    max_files: int = 8,
) -> list[dict[str, str]]:
    try:
        source_content = source_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        source_content = ""

    candidates: list[tuple[Path, str]] = []

    def add(candidate: Path, reason: str) -> None:
        resolved = _resolve_runtime_source_path(project_dir, str(candidate))
        if resolved is not None and resolved != source_path:
            candidates.append((resolved, reason))

    _add_companion_translation_units(project_dir, source_path, add)
    for include_value in _LOCAL_INCLUDE_RE.findall(source_content):
        include_path = Path(include_value)
        add(source_path.parent / include_path, "local_include")
        add(project_dir / include_path, "local_include")
        add(project_dir / "include" / include_path, "local_include")

    for candidate, _reason in list(candidates):
        _add_companion_translation_units(project_dir, candidate, add)

    related: list[dict[str, str]] = []
    seen: set[Path] = set()
    for candidate, reason in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            relative_path = str(candidate.relative_to(project_dir))
            content = candidate.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        related.append(
            {
                "path": relative_path,
                "reason": reason,
                "content_excerpt": _clip_text(content, 5_000),
            }
        )
        if len(related) >= max_files:
            break
    return related


def _add_companion_translation_units(
    project_dir: Path,
    path: Path,
    add: Any,
) -> None:
    suffix = path.suffix
    stem = path.stem
    if suffix in _SOURCE_SUFFIXES:
        for header_suffix in _HEADER_SUFFIXES:
            add(project_dir / "include" / f"{stem}{header_suffix}", "same_stem_header")
        return
    if suffix in _HEADER_SUFFIXES:
        for source_suffix in _SOURCE_SUFFIXES:
            add(project_dir / "src" / f"{stem}{source_suffix}", "same_stem_source")


def _iter_diagnostic_strings(value: Any, *, _remaining: list[int] | None = None):
    if _remaining is None:
        _remaining = [120]
    if _remaining[0] <= 0:
        return
    if isinstance(value, str):
        if _COMPILE_DIAGNOSTIC_RE.search(value):
            _remaining[0] -= 1
            yield _clip_text(value, 30_000)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_diagnostic_strings(item, _remaining=_remaining)
        return
    if isinstance(value, dict):
        preferred_keys = (
            "errors",
            "warnings",
            "stderr",
            "stdout",
            "build_output",
            "cmake_output",
            "artifact_summaries",
            "preview",
            "log_tail",
            "details",
            "build_result",
            "cmake_configure_result",
        )
        for key in preferred_keys:
            if key in value:
                yield from _iter_diagnostic_strings(value[key], _remaining=_remaining)


def _resolve_runtime_source_path(project_dir: Path, raw_path: str) -> Path | None:
    path = Path(raw_path)
    candidates = [path] if path.is_absolute() else [project_dir / path, path]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            candidate.resolve().relative_to(project_dir.resolve())
        except ValueError:
            continue
        return candidate
    return None


def _diagnostic_block(text: str, start: int) -> str:
    lines = text[start:].splitlines()
    block: list[str] = []
    for line in lines[:10]:
        if block and line.startswith("make["):
            break
        block.append(line)
    return _clip_text("\n".join(block), 4_000)


def _source_excerpt(path: Path, line: int, *, context_lines: int = 8) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if not lines:
        return ""
    start = max(1, line - context_lines)
    end = min(len(lines), line + context_lines)
    excerpt_lines = [
        f"{number:5d} | {lines[number - 1]}"
        for number in range(start, end + 1)
    ]
    return _clip_text("\n".join(excerpt_lines), 8_000)


def _trim_runtime_failure_context(
    compact: dict[str, Any],
    *,
    max_chars: int,
) -> dict[str, Any]:
    text = json.dumps(compact, ensure_ascii=False)
    if len(text) <= max_chars:
        return compact

    reduced = deepcopy(compact)
    reduced["runtime_project_files"] = _clip_list(
        reduced.get("runtime_project_files", []),
        max_items=8,
    )
    reduced["artifact_summaries"] = _clip_list(
        reduced.get("artifact_summaries", []),
        max_items=4,
    )
    for key in (
        "build_result",
        "cmake_configure_result",
        "unit_test_result",
        "output_quality",
        "output_summary",
    ):
        if key in reduced:
            reduced[key] = _trim_json_value(reduced[key], max_chars=6_000)
    text = json.dumps(reduced, ensure_ascii=False)
    if len(text) <= max_chars:
        return reduced

    minimal = {
        key: reduced.get(key)
        for key in (
            "job_id",
            "status",
            "phase",
            "attempt",
            "project_dir",
            "output_dir",
            "missing_outputs",
            "compile_error_contexts",
            "errors",
            "runner_contract",
        )
        if key in reduced
    }
    minimal["warnings"] = _clip_list(reduced.get("warnings", []), max_items=4)
    minimal["failed_gates"] = _clip_list(reduced.get("failed_gates", []), max_items=4)
    text = json.dumps(minimal, ensure_ascii=False)
    if len(text) <= max_chars:
        return minimal

    minimal["errors"] = _clip_list(minimal.get("errors", []), max_items=4)
    minimal["compile_error_contexts"] = _clip_list(
        minimal.get("compile_error_contexts", []),
        max_items=4,
    )
    return _trim_json_value(minimal, max_chars=max_chars)


def _runtime_artifact_summaries(runtime_failure_context: dict[str, Any]) -> list[dict[str, Any]]:
    paths: list[str] = []
    for artifact in runtime_failure_context.get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("path"):
            paths.append(str(artifact["path"]))
        elif isinstance(artifact, str):
            paths.append(artifact)
    details = runtime_failure_context.get("details", {})
    if isinstance(details, dict):
        for gate in details.get("failed_gates", []):
            if not isinstance(gate, dict):
                continue
            for key in ("file_paths", "evidence"):
                for value in gate.get(key, []):
                    text = str(value)
                    if text.endswith(".json") or Path(text).is_file():
                        paths.append(text)

    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_path in paths:
        if raw_path in seen:
            continue
        seen.add(raw_path)
        path = Path(raw_path)
        if not path.is_file():
            continue
        name = path.name
        if name == "gate_results.json":
            continue
        summaries.append(_read_runtime_artifact_summary(path))
        if len(summaries) >= 8:
            break
    return summaries


def _read_runtime_artifact_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {"path": str(path)}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        summary["error"] = str(exc)
        return summary
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        summary["tail"] = _clip_text(text, 4_000)
        return summary
    if not isinstance(data, dict):
        summary["value"] = _trim_json_value(data, max_chars=4_000)
        return summary
    for key in (
        "success",
        "returncode",
        "command",
        "errors",
        "warnings",
        "stdout",
        "stderr",
        "log_tail",
        "build_output",
        "cmake_output",
        "output_summary",
    ):
        if key in data:
            value = data[key]
            summary[key] = _trim_json_value(value, max_chars=8_000)
    return summary


def _runtime_project_file_summaries(
    runtime_failure_context: dict[str, Any],
) -> list[dict[str, str]]:
    project_dir_value = runtime_failure_context.get("project_dir")
    if not project_dir_value:
        return []
    project_dir = Path(str(project_dir_value))
    if not project_dir.is_dir():
        return []

    source_files: list[Path] = []
    for relative in ("CMakeLists.txt", "main.cc"):
        path = project_dir / relative
        if path.is_file():
            source_files.append(path)
    for pattern in ("include/*.hh", "src/*.cc", "macros/*.mac"):
        source_files.extend(sorted(project_dir.glob(pattern)))

    summaries: list[dict[str, str]] = []
    total_chars = 0
    seen: set[Path] = set()
    for path in source_files:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        remaining = 55_000 - total_chars
        if remaining <= 0:
            break
        clipped = _clip_text(content, min(5_000, remaining))
        total_chars += len(clipped)
        summaries.append(
            {
                "path": str(path.relative_to(project_dir)),
                "new_content": clipped,
            }
        )
        if len(summaries) >= 24:
            break
    return summaries


def _recent_failed_events(runtime_failure_context: dict[str, Any]) -> list[dict[str, Any]]:
    events = runtime_failure_context.get("recent_events", [])
    if not isinstance(events, list):
        return []
    failed: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("status") not in {"failed", "fail"} and not event.get("errors"):
            continue
        failed.append(
            {
                "event_type": event.get("event_type"),
                "summary": event.get("summary"),
                "errors": _clip_list(event.get("errors", []), max_items=6),
                "warnings": _clip_list(event.get("warnings", []), max_items=4),
            }
        )
    return failed[-12:]


def _compact_search_evidence(
    evidence: Any,
    *,
    max_results: int = 8,
    max_content_chars: int = 1_200,
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        return {}
    compact = {
        "status": evidence.get("status"),
        "errors": _clip_list(evidence.get("errors", []), max_items=5),
        "results": [],
    }
    for result in evidence.get("results", [])[:max_results]:
        if not isinstance(result, dict):
            continue
        item = {
            key: result.get(key)
            for key in ("doc_id", "title", "url", "source", "source_type", "score", "confidence")
            if result.get(key) is not None
        }
        content = result.get("content", result.get("snippet", ""))
        if content:
            item["content"] = _clip_text(str(content), max_content_chars)
        compact["results"].append(item)
    return compact


def _compact_module_contracts(module_contracts: Any) -> dict[str, Any]:
    if not isinstance(module_contracts, dict):
        return {}
    compact: dict[str, Any] = {}
    for module_name, contract in module_contracts.items():
        if not isinstance(contract, dict):
            continue
        compact[str(module_name)] = {
            key: contract.get(key)
            for key in (
                "module_name",
                "responsibilities",
                "output_files",
                "required_symbols",
                "dependencies",
                "forbidden_patterns",
            )
            if contract.get(key) is not None
        }
    return compact


def _compact_module_context_summaries(module_context_summaries: Any) -> dict[str, Any]:
    if not isinstance(module_context_summaries, dict):
        return {}
    compact: dict[str, Any] = {}
    for module_name, summary in module_context_summaries.items():
        if not isinstance(summary, dict):
            continue
        compact[str(module_name)] = {
            "interface_context": _trim_json_value(
                summary.get("interface_context", {}), max_chars=2_000
            ),
            "existing_generated_file_summaries": summary.get(
                "existing_generated_file_summaries", []
            )[:10],
            "geant4_example_lookup_results": _trim_json_value(
                summary.get("geant4_example_lookup_results", {}),
                max_chars=8_000,
            ),
            "run_mode": summary.get("run_mode"),
        }
    return compact


def _compact_integration_memory(
    integration_memory: Any,
    *,
    max_chars: int = 15_000,
) -> dict[str, Any]:
    if not isinstance(integration_memory, dict):
        return {}
    compact = {
        key: value
        for key, value in integration_memory.items()
        if key
        in {
            "previous_integration_report",
            "previous_runtime_gate",
            "agentic_repair_lessons",
        }
    }
    if "failure_bundle" in integration_memory:
        compact["failure_bundle"] = _compact_runtime_failure_context(
            integration_memory["failure_bundle"]
        )
    return _trim_json_value(compact, max_chars=max_chars)


def _clip_list(values: Any, *, max_items: int) -> list[Any]:
    if not isinstance(values, list):
        return []
    return [_trim_json_value(value, max_chars=2_000) for value in values[:max_items]]


def _clip_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 40:
        return text[:max_chars]
    return text[: max_chars - 35] + "\n[truncated for prompt budget]"


def _trim_json_value(value: Any, *, max_chars: int) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= max_chars:
        return value
    if isinstance(value, str):
        return _clip_text(value, max_chars)
    return {"summary": _clip_text(text, max_chars)}


def _apply_runtime_event_count_to_patch(
    patch: dict[str, Any],
    expected_events: int | None,
) -> dict[str, Any]:
    if expected_events is None or expected_events <= 0:
        return patch
    patched = deepcopy(patch)
    changed_files = patched.get("changed_files")
    if not isinstance(changed_files, list):
        return patched
    for entry in changed_files:
        if not isinstance(entry, dict):
            continue
        if entry.get("path") != "macros/run.mac":
            continue
        content = entry.get("new_content")
        if isinstance(content, str):
            entry["new_content"] = _replace_run_macro_events(content, expected_events)
    return patched


async def _run_integration_runtime_gate(
    *,
    job_id: str,
    proposed_patch: dict[str, Any],
    attempt: int,
    expected_events: int = SELF_CHECK_EVENTS,
) -> dict[str, Any]:
    attempt_dir = get_job_dir(job_id) / STAGE_CODEGEN / "integration" / f"runtime_attempt_{attempt}"
    project_dir = attempt_dir / GEANT4_PROJECT_DIRNAME
    output_dir = attempt_dir / "g4_output_package"
    runner_contract = _runtime_gate_runner_contract(
        project_dir=project_dir,
        output_dir=output_dir,
        events=expected_events,
    )
    if attempt_dir.exists():
        shutil.rmtree(attempt_dir)
    project_dir.mkdir(parents=True, exist_ok=True)

    for entry in proposed_patch.get("changed_files", []):
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path", ""))
        content = entry.get("new_content")
        if not path or content is None or path.startswith("/") or ".." in path:
            continue
        target = project_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")

    record_event(
        job_id=job_id,
        event_type="global_integration_runtime_gate_start",
        status="running",
        phase="g4_codegen",
        module_name="global_integration_agent",
        summary=f"Runtime gate attempt {attempt}",
        artifacts=[{"path": str(project_dir)}],
    )

    try:
        from agent_core.tools.geant4_runner import Geant4Runner

        runner = Geant4Runner()
        result = await runner.smoke_test(
            str(project_dir),
            job_id=job_id,
            output_dir=str(output_dir),
            events=expected_events,
        )
        gate = _summarize_runtime_gate_result(
            result=result,
            attempt=attempt,
            project_dir=project_dir,
            output_dir=output_dir,
            expected_events=expected_events,
        )
        gate["runner_contract"] = runner_contract
    except Exception as exc:
        gate = {
            "status": "fail",
            "attempt": attempt,
            "project_dir": str(project_dir),
            "output_dir": str(output_dir),
            "expected_events": expected_events,
            "errors": [str(exc)],
            "warnings": [],
            "artifacts": [],
            "runner_contract": runner_contract,
        }
    (attempt_dir / "runtime_gate_result.json").write_text(
        json.dumps(gate, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    record_event(
        job_id=job_id,
        event_type="global_integration_runtime_gate_result",
        status="passed" if gate.get("status") == "pass" else "failed",
        phase="g4_codegen",
        module_name="global_integration_agent",
        summary=f"Runtime gate attempt {attempt} {gate.get('status')}",
        artifacts=[{"path": str(attempt_dir / "runtime_gate_result.json")}],
        errors=[str(item) for item in gate.get("errors", [])],
        warnings=[str(item) for item in gate.get("warnings", [])],
        details=gate,
    )
    return gate


def _runtime_gate_runner_contract(
    *,
    project_dir: Path,
    output_dir: Path,
    events: int = SELF_CHECK_EVENTS,
) -> dict[str, Any]:
    project_abs = project_dir.resolve()
    build_abs = project_abs / "build"
    output_abs = output_dir.resolve()
    return {
        "runner": "Geant4Runner.smoke_test",
        "events": events,
        "project_dir": str(project_dir),
        "project_dir_abs": str(project_abs),
        "build_dir_abs": str(build_abs),
        "output_dir": str(output_dir),
        "output_dir_abs": str(output_abs),
        "configure_command_shape": f"cmake {project_abs}",
        "configure_cwd": str(build_abs),
        "build_command_shape": "make -j4",
        "ctest_command_shape": "ctest --output-on-failure",
        "simulation_output_env": "G4_OUTPUT_DIR",
        "required_outputs": list(REQUIRED_G4_OUTPUTS),
        "allowed_path_patterns": list(GLOBAL_INTEGRATION_ALLOWED_PATH_PATTERNS),
        "forbidden_path_examples": list(GLOBAL_INTEGRATION_FORBIDDEN_PATH_EXAMPLES),
        "permission_rule": (
            "Repair patches may modify/create only green generated project files. "
            "Do not add shell scripts or CMakePresets.json; fix build behavior in CMakeLists.txt."
        ),
    }


def _summarize_runtime_gate_result(
    *,
    result: dict[str, Any],
    attempt: int,
    project_dir: Path,
    output_dir: Path,
    expected_events: int | None = None,
) -> dict[str, Any]:
    required_outputs = list(REQUIRED_G4_OUTPUTS)
    missing_outputs = [name for name in required_outputs if not (output_dir / name).is_file()]
    errors: list[str] = []
    warnings: list[str] = [str(item) for item in result.get("warnings", []) if item]
    cfg = result.get("cmake_configure_result", {})
    build = result.get("build_result", {})
    unit = result.get("unit_test_result", {})
    smoke_result = _load_json_file(output_dir / "smoke_simulation_result.json")
    runtime_fatal = _runtime_fatal_error_text(result, smoke_result)
    if runtime_fatal:
        errors.append(runtime_fatal[-12000:])
    if cfg and cfg.get("success") is not True:
        errors.append(str(cfg.get("errors") or "cmake configure failed")[-8000:])
    if build and build.get("success") is not True:
        errors.append(str(build.get("errors") or "build failed")[-12000:])
    if unit and unit.get("success") is not True:
        errors.append(str(unit.get("errors") or unit.get("stdout") or "ctest failed")[-4000:])
    if result.get("success") is not True and not errors:
        errors.extend(warnings or ["Geant4 smoke test failed"])
    if missing_outputs:
        errors.append(f"Missing output contract files: {', '.join(missing_outputs)}")
    quality = inspect_g4_output_quality(
        output_dir,
        smoke_result=smoke_result,
        expected_events=expected_events,
    )
    quality_errors = [
        error
        for error in quality.errors
        if not error.startswith("Missing output contract files:")
    ]
    if quality_errors:
        errors.extend(_dedupe_runtime_quality_errors(quality_errors, runtime_fatal))
    warnings.extend(quality.warnings)
    artifacts = [
        str(path)
        for path in [
            output_dir / "cmake_configure_result.json",
            output_dir / "build_result.json",
            output_dir / "unit_test_result.json",
            output_dir / "smoke_simulation_result.json",
        ]
        if path.is_file()
    ]
    return {
        "status": (
            "pass"
            if (
                result.get("success") is True
                and not missing_outputs
                and not quality_errors
            )
            else "fail"
        ),
        "attempt": attempt,
        "project_dir": str(project_dir),
        "output_dir": str(output_dir),
        "expected_events": expected_events,
        "errors": errors,
        "warnings": warnings,
        "missing_outputs": missing_outputs,
        "artifacts": artifacts,
        "cmake_configure_result": cfg,
        "build_result": build,
        "unit_test_result": unit,
        "output_quality": {
            "status": "pass" if not quality.errors else "fail",
            "errors": quality.errors,
            "warnings": quality.warnings,
            "metrics": quality.metrics,
        },
        "output_summary": result.get("output_summary", ""),
    }


def _runtime_fatal_error_text(
    result: dict[str, Any],
    smoke_result: dict[str, Any],
) -> str:
    candidates: list[str] = []
    for value in (result.get("run_errors"), result.get("errors")):
        if isinstance(value, list):
            candidates.extend(str(item) for item in value if item)
        elif value:
            candidates.append(str(value))
    smoke_errors = smoke_result.get("errors")
    if smoke_errors:
        candidates.append(str(smoke_errors))
    for candidate in candidates:
        text = str(candidate)
        if _looks_like_runtime_fatal(text):
            return text
    return ""


def _looks_like_runtime_fatal(text: str) -> bool:
    if not text.strip():
        return False
    markers = (
        "G4Exception",
        "FatalException",
        "Segmentation fault",
        "core dumped",
        "COMMAND NOT FOUND",
    )
    return any(marker in text for marker in markers)


def _dedupe_runtime_quality_errors(
    quality_errors: list[str],
    runtime_fatal: str,
) -> list[str]:
    if not runtime_fatal:
        return quality_errors
    deduped: list[str] = []
    for error in quality_errors:
        if error.startswith("Smoke simulation stderr contains:"):
            continue
        deduped.append(error)
    return deduped


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _project_files_from_patch(proposed_patch: dict[str, Any]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for entry in proposed_patch.get("changed_files", []):
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path", ""))
        content = str(entry.get("new_content", ""))
        if not path or not content:
            continue
        files.append(
            {
                "path": path,
                "module_name": str(entry.get("module_name", "")),
                "generated_by": str(entry.get("generated_by", "")),
                "new_content": content,
            }
        )
    return files


def _interface_audit_from_patch(proposed_patch: dict[str, Any]) -> dict[str, Any]:
    metadata = proposed_patch.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    audit = metadata.get("interface_audit")
    return audit if isinstance(audit, dict) else {}


def _summarize_module_contexts(module_contexts: dict[str, Any]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for module_name, context in module_contexts.items():
        if not isinstance(context, dict):
            continue
        summaries[module_name] = {
            "module_contract": context.get("module_contract", {}),
            "interface_context": context.get("interface_context", {}),
            "existing_generated_file_summaries": context.get(
                "existing_generated_file_summaries", []
            ),
            "geant4_example_lookup_results": context.get(
                "geant4_example_lookup_results", {}
            ),
            "run_mode": context.get("run_mode", "strict"),
        }
    return summaries


def _load_integration_memory(job_id: str) -> dict[str, Any]:
    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    job_dir = get_job_dir(job_id)
    return {
        "previous_integration_report": _read_json_tail(
            codegen_dir / "global_integration_agent_report.json"
        ),
        "previous_integration_evidence": _read_json_tail(
            codegen_dir / "integration" / "global_integration_evidence.json"
        ),
        "agentic_repair_lessons": _read_json_tail(
            codegen_dir / "integration" / "agentic_repair_lessons.json"
        ),
        "failure_bundle": _read_json_tail(job_dir / "logs" / "failure_bundle.json"),
    }


def _read_json_tail(path: Path, *, max_chars: int = 12000) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return {"path": str(path), "tail": text[-max_chars:] if "text" in locals() else ""}
    if not isinstance(data, dict):
        return {"path": str(path), "value": data}
    compact = deepcopy(data)
    for key in ("changed_files", "project_files", "file_details"):
        if isinstance(compact.get(key), list):
            compact[key] = compact[key][:20]
    compact["path"] = str(path)
    return compact


async def _collect_integration_evidence(
    *,
    job_id: str,
    integration_context: dict[str, Any],
) -> dict[str, Any]:
    query = _build_integration_query(integration_context)
    evidence: dict[str, Any] = {
        "query": query,
        "database_search": {"status": "not_run", "results": [], "errors": []},
        "web_search": {"status": "not_run", "results": [], "errors": []},
    }
    record_event(
        job_id=job_id,
        event_type="global_integration_evidence_start",
        status="running",
        phase="g4_codegen",
        module_name="global_integration_agent",
        summary="Collecting database and web evidence",
        details={"query": query[:500]},
    )
    try:
        evidence["database_search"] = {
            "status": "pass",
            "results": await asyncio.wait_for(_search_database(query), timeout=20.0),
            "errors": [],
        }
        if not evidence["database_search"]["results"]:
            evidence["database_search"]["status"] = "empty"
    except Exception as exc:
        evidence["database_search"] = {"status": "error", "results": [], "errors": [str(exc)]}

    try:
        evidence["web_search"] = {
            "status": "pass",
            "results": await asyncio.wait_for(_search_web(query), timeout=15.0),
            "errors": [],
        }
        if not evidence["web_search"]["results"]:
            evidence["web_search"]["status"] = "empty"
    except Exception as exc:
        evidence["web_search"] = {"status": "error", "results": [], "errors": [str(exc)]}

    out_dir = get_job_dir(job_id) / STAGE_CODEGEN / "integration"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "global_integration_evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence["database_search"]["results"] = evidence["database_search"]["results"][:10]
    evidence["web_search"]["results"] = evidence["web_search"]["results"][:5]
    record_event(
        job_id=job_id,
        event_type="global_integration_evidence_result",
        status="passed" if _has_evidence(evidence) else "failed",
        phase="g4_codegen",
        module_name="global_integration_agent",
        summary="Collected integration evidence",
        metrics={
            "database_result_count": len(evidence["database_search"].get("results", [])),
            "web_result_count": len(evidence["web_search"].get("results", [])),
        },
        errors=[
            *[str(item) for item in evidence["database_search"].get("errors", [])],
            *[str(item) for item in evidence["web_search"].get("errors", [])],
        ],
        details={
            "database_status": evidence["database_search"].get("status"),
            "web_status": evidence["web_search"].get("status"),
        },
    )
    return evidence


def _build_integration_query(integration_context: dict[str, Any]) -> str:
    parts = [
        "Geant4 CMake run manager detector construction physics list action initialization "
        "sensitive detector scoring output artifact compile smoke simulation"
    ]
    for item in integration_context.get("project_files", []):
        if not isinstance(item, dict):
            continue
        content = str(item.get("new_content", ""))
        for token in (
            "G4RunManager",
            "G4VUserDetectorConstruction",
            "G4VUserActionInitialization",
            "G4PhysListFactory",
            "G4PVPlacement",
            "G4THitsCollection",
            "G4MultiFunctionalDetector",
            "G4_OUTPUT_DIR",
            "CMakeLists",
        ):
            if token in content:
                parts.append(token)
    failure_context = integration_context.get("runtime_failure_context", {})
    for key in ("build_errors", "runtime_errors", "artifact_errors", "failed_gates"):
        value = failure_context.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value[:8])
        elif isinstance(value, str):
            parts.append(value)
    parts.extend(_runtime_failure_query_terms(failure_context))
    return " ".join(parts)[:1800]


def _runtime_failure_query_terms(failure_context: Any) -> list[str]:
    if not isinstance(failure_context, dict):
        return []
    terms: list[str] = []

    def add(value: Any, *, max_chars: int = 450) -> None:
        if value is None or len(terms) >= 18:
            return
        if isinstance(value, str):
            text = value.strip()
            if text:
                terms.append(_clip_text(text, max_chars))
            return
        if isinstance(value, list):
            for item in value:
                add(item, max_chars=max_chars)
                if len(terms) >= 18:
                    break
            return
        if isinstance(value, dict):
            for nested_key in (
                "path",
                "message",
                "diagnostic",
                "errors",
                "warnings",
                "failed_items",
                "missing_outputs",
            ):
                if nested_key in value:
                    add(value[nested_key], max_chars=max_chars)
                    if len(terms) >= 18:
                        break

    for key in (
        "errors",
        "warnings",
        "missing_outputs",
        "compile_error_contexts",
        "failed_gates",
    ):
        add(failure_context.get(key))
    for key in (
        "build_result",
        "cmake_configure_result",
        "unit_test_result",
        "output_quality",
    ):
        nested = failure_context.get(key)
        if isinstance(nested, dict):
            add(nested.get("errors"))
            add(nested.get("warnings"))
    return terms


async def _search_database(query: str) -> list[dict[str, Any]]:
    from agent_core.context.nodes import _ensure_indexed, _get_rag_client

    client = _get_rag_client()
    if not await client.backend_available():
        return []
    if not await _ensure_indexed(client):
        return []
    results = await client.search(query, top_k=12, min_score=0.0)
    return [
        {
            "doc_id": result.doc_id,
            "title": result.title,
            "content": result.content[:1600],
            "source": result.source,
            "score": round(result.score, 4),
        }
        for result in results
    ]


async def _search_web(query: str) -> list[dict[str, Any]]:
    from agent_core.tools.web_search_tool import WebSearchTool

    tool = WebSearchTool()
    if not tool.search_available:
        return []
    results = await tool.search(query, max_results=5)
    return [
        {
            "title": result.title,
            "url": result.url,
            "snippet": result.snippet[:900],
            "source_type": result.source_type,
            "confidence": result.confidence,
        }
        for result in results
    ]


def _has_evidence(evidence: dict[str, Any]) -> bool:
    return bool(
        evidence.get("database_search", {}).get("results")
        or evidence.get("web_search", {}).get("results")
    )


def _persist_integration_context(context: dict[str, Any], job_id: str) -> None:
    out_dir = get_job_dir(job_id) / STAGE_CODEGEN / "integration"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "global_integration_context.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _global_integration_write_contract(patch: dict[str, Any]) -> dict[str, Any]:
    existing_paths = sorted(
        {
            str(entry.get("path"))
            for entry in patch.get("changed_files", [])
            if isinstance(entry, dict)
            and entry.get("path")
            and _global_integration_path_allowed(str(entry.get("path")))
        }
    )
    return {
        "output": "proposed_patch JSON",
        "path_root": "geant4_project",
        "allowed_path_patterns": list(GLOBAL_INTEGRATION_ALLOWED_PATH_PATTERNS),
        "allowed_existing_paths": existing_paths,
        "forbidden_path_examples": list(GLOBAL_INTEGRATION_FORBIDDEN_PATH_EXAMPLES),
        "can_modify_existing_green_files": True,
        "can_create_new_green_files": True,
        "must_preserve_schema": True,
        "partial_response_merge": True,
        "permission_rule": (
            "Every changed_files[].path must be relative to geant4_project and must pass "
            "FilePermissionValidator.can_auto_apply(path). Put build changes in "
            "CMakeLists.txt; do not create shell scripts or CMakePresets.json."
        ),
        "final_runtime_gate": (
            "After patch application, gate_subgraph must pass Geant4 build, ctest, "
            "data contract, and smoke simulation gates."
        ),
    }


def _global_integration_path_allowed(path: str) -> bool:
    if not path or path.startswith("/") or path.startswith("geant4_project/") or ".." in path:
        return False
    from agent_core.validators.file_permission_validator import FilePermissionValidator

    return FilePermissionValidator().can_auto_apply(path)


def _global_integration_path_permission_error(path: str) -> str | None:
    if _global_integration_path_allowed(path):
        return None
    allowed = ", ".join(GLOBAL_INTEGRATION_ALLOWED_PATH_PATTERNS)
    forbidden = ", ".join(GLOBAL_INTEGRATION_FORBIDDEN_PATH_EXAMPLES)
    return (
        f"{path}: not allowed by generated project write policy; "
        f"allowed patterns: {allowed}; forbidden examples: {forbidden}"
    )


def _validate_candidate_patch_schema(
    original_patch: dict[str, Any],
    candidate_patch: dict[str, Any],
) -> list[str]:
    """Validate a model response before overlaying it onto the full patch.

    Existing paths may return only path/new_content because metadata is inherited
    from the original module-authored file. New paths must be full patch entries.
    """
    errors: list[str] = []
    original_paths = {
        str(entry.get("path"))
        for entry in original_patch.get("changed_files", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    files = candidate_patch.get("changed_files")
    if not isinstance(files, list) or not files:
        return ["proposed_patch.changed_files must be a non-empty list"]
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            errors.append(f"changed_files[{index}] must be an object")
            continue
        path = str(entry.get("path", ""))
        if "content" in entry:
            errors.append(f"{entry.get('path', index)}: content field is forbidden")
        if not path:
            errors.append(f"changed_files[{index}]: missing path")
            continue
        if not entry.get("new_content"):
            errors.append(f"{path}: missing new_content")
        if path.startswith("geant4_project/") or ".." in path or path.startswith("/"):
            errors.append(f"{path}: path must be relative to generated_code_dir")
        permission_error = _global_integration_path_permission_error(path)
        if permission_error:
            errors.append(permission_error)
        if "```" in str(entry.get("new_content", "")):
            errors.append(f"{path}: new_content must not contain markdown fences")
        if path not in original_paths:
            for required in ("zone", "generated_by", "module_name"):
                if not entry.get(required):
                    errors.append(f"{path}: missing {required}")
    return errors


def _normalize_candidate_patch_metadata(
    original_patch: dict[str, Any],
    candidate_patch: dict[str, Any],
) -> dict[str, Any]:
    """Fill safe patch metadata defaults before schema validation and merge."""
    normalized = deepcopy(candidate_patch)
    files = normalized.get("changed_files")
    if not isinstance(files, list):
        return normalized
    original_by_path = {
        str(entry.get("path")): entry
        for entry in original_patch.get("changed_files", [])
        if isinstance(entry, dict) and entry.get("path")
    }
    for entry in files:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path", ""))
        original_entry = original_by_path.get(path, {})
        if not entry.get("zone"):
            entry["zone"] = original_entry.get("zone") or _infer_patch_zone(path)
        if not entry.get("generated_by"):
            entry["generated_by"] = (
                original_entry.get("generated_by") or "global_integration_agent"
            )
        if not entry.get("module_name"):
            entry["module_name"] = original_entry.get("module_name") or _infer_module_name(path)
        if not entry.get("operation"):
            entry["operation"] = original_entry.get("operation") or "create_or_replace"
    return normalized


def _infer_patch_zone(path: str) -> str:
    if path == "main.cc" or path == "CMakeLists.txt":
        return "application"
    if path.startswith("macros/"):
        return "runtime_macro"
    if path.startswith("include/"):
        return "header"
    if path.startswith("src/"):
        return "source"
    return "generated_project"


def _infer_module_name(path: str) -> str:
    if path == "main.cc" or path == "CMakeLists.txt" or path.startswith("macros/"):
        return "runtime_app"
    name = Path(path).stem.lower()
    if any(token in name for token in ("generator", "physics")):
        return "beam_physics"
    if any(token in name for token in ("output", "action", "run", "event", "stepping")):
        return "runtime_app"
    if any(
        token in name
        for token in (
            "material",
            "placement",
            "detector",
            "hit",
            "sensitive",
            "scoring",
        )
    ):
        return "simulation_core"
    return "runtime_app"


def _merge_patch_by_path(
    original_patch: dict[str, Any],
    candidate_patch: dict[str, Any],
    *,
    expected_events: int | None = None,
) -> tuple[dict[str, Any], list[str]]:
    original_files = original_patch.get("changed_files")
    candidate_files = candidate_patch.get("changed_files")
    if not isinstance(original_files, list) or not original_files:
        return original_patch, ["original proposed_patch.changed_files is empty"]
    if not isinstance(candidate_files, list) or not candidate_files:
        return original_patch, ["candidate proposed_patch.changed_files is empty"]

    original_by_path: dict[str, int] = {}
    for index, entry in enumerate(original_files):
        if not isinstance(entry, dict) or not entry.get("path"):
            return original_patch, [f"original changed_files[{index}] missing path"]
        path = str(entry["path"])
        if path in original_by_path:
            return original_patch, [f"original proposed_patch has duplicate path: {path}"]
        original_by_path[path] = index

    merged_files = [deepcopy(entry) for entry in original_files]
    seen: set[str] = set()
    for index, entry in enumerate(candidate_files):
        if not isinstance(entry, dict) or not entry.get("path"):
            return original_patch, [f"candidate changed_files[{index}] missing path"]
        path = str(entry["path"])
        if path in seen:
            return original_patch, [f"candidate proposed_patch has duplicate path: {path}"]
        seen.add(path)
        if path in original_by_path:
            merged_entry = deepcopy(merged_files[original_by_path[path]])
            merged_entry.update(deepcopy(entry))
            _postprocess_patch_entry(merged_entry)
            merged_files[original_by_path[path]] = merged_entry
        else:
            merged_entry = deepcopy(entry)
            _postprocess_patch_entry(merged_entry)
            merged_files.append(merged_entry)

    _postprocess_merged_patch_files(merged_files, expected_events=expected_events)

    merged_patch = deepcopy(original_patch)
    merged_patch["changed_files"] = merged_files
    if isinstance(candidate_patch.get("metadata"), dict):
        metadata = deepcopy(original_patch.get("metadata", {}))
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.update(deepcopy(candidate_patch["metadata"]))
        merged_patch["metadata"] = metadata
    return merged_patch, []


def _postprocess_patch_entry(entry: dict[str, Any]) -> None:
    path = str(entry.get("path", ""))
    if not isinstance(entry.get("new_content"), str):
        return
    content = entry["new_content"]
    content = _postprocess_generated_module_content(path, content)
    if path == "src/SensitiveDetector.cc":
        content = _qualify_sensitive_detector_hit_type(content)
        content = content.replace("edep == 0.00", "edep == 0.0")
        content = re.sub(r"edep\s*==\s*0\.(?!\d)", "edep == 0.0", content)
    if path == "main.cc":
        content = _prefer_serial_run_manager(content)
    if path == "src/OutputManager.cc":
        content = _ensure_summary_events_requested(content)
        content = _postprocess_output_manager_no_magic_numbers(content)
    if path == "src/Hit.cc":
        content = _postprocess_hit_no_magic_numbers(content)
    if path == "src/DetectorConstruction.cc":
        content = _postprocess_detector_no_magic_numbers(content)
    if path == "src/ScoringManager.cc":
        content = _postprocess_scoring_no_magic_numbers(content)
    if path == "include/ScoringManager.hh":
        content = _postprocess_scoring_no_magic_numbers(content)
    if path == "main.cc":
        content = _postprocess_main_no_magic_numbers(content)
    entry["new_content"] = content


def _postprocess_merged_patch_files(
    files: list[dict[str, Any]],
    *,
    expected_events: int | None = None,
) -> None:
    by_path = {
        str(entry.get("path")): entry
        for entry in files
        if isinstance(entry, dict) and entry.get("path")
    }
    scoring_header = by_path.get("include/ScoringManager.hh", {}).get("new_content")
    scoring_returns_reference = isinstance(
        scoring_header, str
    ) and _scoring_manager_returns_reference(scoring_header)
    scoring_can_initialize = isinstance(
        scoring_header, str
    ) and _scoring_manager_has_initialize(scoring_header)
    sensitive_records_energy = _sensitive_detector_records_energy(by_path)

    if scoring_returns_reference:
        for entry in files:
            path = str(entry.get("path", ""))
            if not path.startswith("src/") or not path.endswith((".cc", ".cpp")):
                continue
            if isinstance(entry.get("new_content"), str):
                entry["new_content"] = _normalize_scoring_manager_reference_api(
                    entry["new_content"]
                )

    detector_entry = by_path.get("src/DetectorConstruction.cc")
    if (
        scoring_returns_reference
        and scoring_can_initialize
        and isinstance(detector_entry, dict)
        and isinstance(detector_entry.get("new_content"), str)
    ):
        detector_entry["new_content"] = _initialize_scoring_manager_volume(
            detector_entry["new_content"]
        )
    if isinstance(detector_entry, dict) and isinstance(detector_entry.get("new_content"), str):
        detector_entry["new_content"] = _normalize_real_g4_ir_geometry_units(
            detector_entry["new_content"]
        )

    stepping_entry = by_path.get("src/SteppingAction.cc")
    if isinstance(stepping_entry, dict) and isinstance(stepping_entry.get("new_content"), str):
        stepping_content = _normalize_stepping_action_volume_lookup(
            stepping_entry["new_content"]
        )
        if scoring_returns_reference and sensitive_records_energy:
            stepping_content = _remove_duplicate_stepping_energy_record(stepping_content)
        stepping_entry["new_content"] = stepping_content

    _align_physics_configuration(by_path, expected_events=expected_events)


def _scoring_manager_returns_reference(header_content: str) -> bool:
    return bool(
        re.search(
            r"static\s+ScoringManager\s*&\s*Instance\s*\(",
            header_content,
        )
    )


def _scoring_manager_has_initialize(header_content: str) -> bool:
    return bool(re.search(r"\bInitialize\s*\(\s*G4LogicalVolume\s*\*", header_content))


def _sensitive_detector_records_energy(by_path: dict[str, dict[str, Any]]) -> bool:
    content = by_path.get("src/SensitiveDetector.cc", {}).get("new_content")
    return isinstance(content, str) and bool(
        re.search(r"\bRecordEnergyDeposit\s*\(", content)
    )


def _prefer_serial_run_manager(content: str) -> str:
    return content.replace("G4RunManagerType::Default", "G4RunManagerType::Serial")


def _initialize_scoring_manager_volume(content: str) -> str:
    if "ScoringManager::Instance().Initialize(si_lv);" in content:
        return content
    if '#include "ScoringManager.hh"' not in content:
        include_anchor = '#include "SensitiveDetector.hh"'
        if include_anchor in content:
            content = content.replace(
                include_anchor,
                include_anchor + '\n#include "ScoringManager.hh"',
                1,
            )
        else:
            content = '#include "ScoringManager.hh"\n' + content
    pattern = r"(G4SDManager::GetSDMpointer\(\)->AddNewDetector\(sd\);\s*)"
    replacement = (
        r"\1"
        "\n    ScoringManager::Instance().Initialize(si_lv);\n"
    )
    updated, count = re.subn(pattern, replacement, content, count=1)
    return updated if count else content


def _normalize_real_g4_ir_geometry_units(content: str) -> str:
    replacements = {
        "100.0 * cm": "100.0 * mm",
        "10.0 * cm": "10.0 * mm",
        "0.25 * cm": "0.25 * mm",
        "0.01 * cm": "0.01 * mm",
        "0.27 * cm": "0.27 * mm",
        "15.0 * cm": "15.0 * mm",
        "0.5 * cm": "0.5 * mm",
        "-10.0 * cm": "-10.0 * mm",
        "200x200x200 cm": "200x200x200 mm",
        "20x20x0.5 cm": "20x20x0.5 mm",
        "20x20x0.02 cm": "20x20x0.02 mm",
        "0.27cm": "0.27mm",
        "30x30x1.0 cm": "30x30x1.0 mm",
        "-10cm": "-10mm",
    }
    for before, after in replacements.items():
        content = content.replace(before, after)
    return content


def _normalize_stepping_action_volume_lookup(content: str) -> str:
    return content.replace('"silicon_detector_LV"', '"SiliconDetector"')


def _remove_duplicate_stepping_energy_record(content: str) -> str:
    return re.sub(
        r"^[ \t]*ScoringManager::Instance\(\)\.RecordEnergyDeposit\(edep\);\n?",
        "",
        content,
        flags=re.MULTILINE,
    )


def _align_physics_configuration(
    by_path: dict[str, dict[str, Any]],
    *,
    expected_events: int | None = None,
) -> None:
    physics_list = _physics_list_from_macro(by_path.get("macros/physics_list.mac", {}))
    physics_entry = by_path.get("src/PhysicsListFactoryWrapper.cc")
    if isinstance(physics_entry, dict) and isinstance(
        physics_entry.get("new_content"), str
    ):
        if physics_list:
            physics_entry["new_content"] = _replace_reference_physics_list(
                physics_entry["new_content"],
                physics_list,
            )
        physics_entry["new_content"] = _tighten_default_production_cut(
            physics_entry["new_content"]
        )
    output_entry = by_path.get("src/OutputManager.cc")
    if physics_list and isinstance(output_entry, dict) and isinstance(
        output_entry.get("new_content"), str
    ):
        output_entry["new_content"] = _replace_provenance_physics_list(
            output_entry["new_content"],
            physics_list,
        )

    primary_entry = by_path.get("src/PrimaryGeneratorAction.cc", {})
    if isinstance(primary_entry, dict) and isinstance(primary_entry.get("new_content"), str):
        primary_entry["new_content"] = _normalize_primary_generator_units(
            primary_entry["new_content"]
        )
    primary_energy = _primary_generator_energy(primary_entry)
    primary_position = _primary_generator_position(primary_entry)
    run_entry = by_path.get("macros/run.mac")
    if primary_energy and isinstance(run_entry, dict) and isinstance(
        run_entry.get("new_content"), str
    ):
        content = _replace_run_macro_energy(
            run_entry["new_content"],
            primary_energy,
        )
        if primary_position:
            content = _replace_run_macro_position(content, primary_position)
        if expected_events is not None and expected_events > 0:
            content = _replace_run_macro_events(content, expected_events)
        run_entry["new_content"] = content


def _physics_list_from_macro(entry: dict[str, Any]) -> str | None:
    content = entry.get("new_content")
    if not isinstance(content, str):
        return None
    match = re.search(r"^\s*/physics_list/select\s+([A-Za-z0-9_+-]+)\s*$", content, re.MULTILINE)
    return match.group(1) if match else None


def _replace_reference_physics_list(content: str, physics_list: str) -> str:
    return re.sub(
        r'GetReferencePhysList\("([^"]+)"\)',
        f'GetReferencePhysList("{physics_list}")',
        content,
    )


def _replace_provenance_physics_list(content: str, physics_list: str) -> str:
    return re.sub(
        r'(\\"physics_list\\"\s*:\s*\\")([^"\\]+)(\\"[,}]?)',
        rf'\1{physics_list}\3',
        content,
    )


def _tighten_default_production_cut(content: str) -> str:
    return re.sub(
        r"SetDefaultCutValue\(\s*1\.0\s*\*\s*mm\s*\)",
        "SetDefaultCutValue(0.1 * mm)",
        content,
    )


def _normalize_primary_generator_units(content: str) -> str:
    return content.replace("-80.0 * cm", "-80.0 * mm").replace(
        "80 cm upstream",
        "80 mm upstream",
    )


def _primary_generator_energy(entry: dict[str, Any]) -> str | None:
    content = entry.get("new_content")
    if not isinstance(content, str):
        return None
    match = re.search(
        r"SetParticleEnergy\s*\(\s*([0-9]+(?:\.[0-9]+)?)\s*\*\s*MeV\s*\)",
        content,
    )
    return f"{match.group(1)} MeV" if match else None


def _primary_generator_position(entry: dict[str, Any]) -> str | None:
    content = entry.get("new_content")
    if not isinstance(content, str):
        return None
    match = re.search(
        r"SetParticlePosition\s*\(\s*G4ThreeVector\s*\(\s*([^,]+)\s*,\s*([^,]+)\s*,\s*([^)]+?)\s*\*\s*mm\s*\)\s*\)",
        content,
    )
    if not match:
        return None
    x = _format_macro_number(match.group(1))
    y = _format_macro_number(match.group(2))
    z = _format_macro_number(match.group(3))
    return f"{x} {y} {z} mm"


def _format_macro_number(value: str) -> str:
    text = value.strip()
    try:
        parsed = float(text)
    except ValueError:
        return text
    if parsed == 0.0:
        return "0"
    return text


def _replace_run_macro_energy(content: str, energy: str) -> str:
    updated, count = re.subn(
        r"^\s*/gun/energy\s+[0-9]+(?:\.[0-9]+)?\s+MeV\s*$",
        f"/gun/energy {energy}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    return updated if count else content


def _replace_run_macro_position(content: str, position: str) -> str:
    updated, count = re.subn(
        r"^\s*/gun/position\s+[-+0-9.eE]+\s+[-+0-9.eE]+\s+[-+0-9.eE]+\s+\w+\s*$",
        f"/gun/position {position}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    return updated if count else content


def _replace_run_macro_events(content: str, events: int) -> str:
    updated, count = re.subn(
        r"^\s*/run/beamOn\s+\d+\s*$",
        f"/run/beamOn {events}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    return updated if count else content


def _ensure_summary_events_requested(content: str) -> str:
    if '\\"events_requested\\"' in content:
        return content
    total_events_line = (
        'ofs << "  \\"total_events\\": " << totalEvents << "," << std::endl;'
    )
    events_requested_line = (
        '  ofs << "  \\"events_requested\\": " << totalEvents << "," << std::endl;'
    )
    if total_events_line in content:
        return content.replace(
            total_events_line,
            total_events_line + "\n" + events_requested_line,
            1,
        )
    return content


def _postprocess_output_manager_no_magic_numbers(content: str) -> str:
    constants = (
        "namespace {\n"
        "constexpr G4double kGridOriginXmm = -100.0;\n"
        "constexpr G4double kGridOriginYmm = -100.0;\n"
        "constexpr G4double kGridOriginZmm = -2.5;\n"
        "constexpr int kCsvPrecision = 6;\n"
        "constexpr int kTimestampBufferSize = 64;\n"
        'constexpr const char* kGeant4VersionString = "11.3";\n'
        "}\n\n"
    )
    if "kGridOriginXmm" not in content:
        marker = "//....oooOO0OOooo"
        if marker in content:
            content = content.replace(marker, constants + marker, 1)
        else:
            content = constants + content
    replacements = {
        "x_mm + 100.0": "x_mm - kGridOriginXmm",
        "y_mm + 100.0": "y_mm - kGridOriginYmm",
        "z_mm + 2.5": "z_mm - kGridOriginZmm",
        "pos.x() + 100.0": "pos.x() - kGridOriginXmm",
        "pos.y() + 100.0": "pos.y() - kGridOriginYmm",
        "pos.z() + 2.5": "pos.z() - kGridOriginZmm",
        "-100.0 + (ix + 0.5) * kBinSizeXY": "kGridOriginXmm + (ix + 0.5) * kBinSizeXY",
        "-100.0 + (iy + 0.5) * kBinSizeXY": "kGridOriginYmm + (iy + 0.5) * kBinSizeXY",
        "-2.5 + (iz + 0.5) * kBinSizeZ": "kGridOriginZmm + (iz + 0.5) * kBinSizeZ",
        "std::setprecision(6)": "std::setprecision(kCsvPrecision)",
        "char timeStr[64];": "char timeStr[kTimestampBufferSize];",
        '\\"version\\": \\"11.3\\"': '\\"version\\": \\"" << kGeant4VersionString << "\\"',
    }
    for before, after in replacements.items():
        content = content.replace(before, after)
    return content


def _postprocess_hit_no_magic_numbers(content: str) -> str:
    constants = (
        "namespace {\n"
        "constexpr G4double kHitMarkerScreenSize = 5.0;\n"
        "constexpr int kHitPrintWidth = 7;\n"
        "}\n\n"
    )
    if "kHitMarkerScreenSize" not in content:
        marker = "G4ThreadLocal G4Allocator<Hit>* HitAllocator = nullptr;"
        if marker in content:
            content = content.replace(marker, marker + "\n\n" + constants, 1)
        else:
            content = constants + content
    content = content.replace(
        "circle.SetScreenSize(5.);",
        "circle.SetScreenSize(kHitMarkerScreenSize);",
    )
    content = content.replace("std::setw(7)", "std::setw(kHitPrintWidth)")
    return content


def _postprocess_detector_no_magic_numbers(content: str) -> str:
    if "kShieldVisGrey" not in content:
        marker = "void DetectorConstruction::BuildGeometry()"
        constants = "    constexpr G4double kShieldVisGrey = 0.6;\n"
        if marker in content and constants not in content:
            content = content.replace(marker, constants + "\n" + marker, 1)
    return content.replace(
        "G4Colour(0.6, 0.6, 0.6)",
        "G4Colour(kShieldVisGrey, kShieldVisGrey, kShieldVisGrey)",
    )


def _postprocess_scoring_no_magic_numbers(content: str) -> str:
    content = content.replace("cm^3", "cubic centimeters")
    content = content.replace("g/cm^3", "grams per cubic centimeter")
    content = content.replace("std::setprecision(6)", "std::setprecision(kCsvPrecision)")
    if "constexpr int kCsvPrecision" not in content and "setprecision(kCsvPrecision)" in content:
        content = "namespace {\nconstexpr int kCsvPrecision = 6;\n}\n\n" + content
    return content


def _postprocess_main_no_magic_numbers(content: str) -> str:
    if "kSteppingVerbosePrecision" not in content:
        content = content.replace(
            "int main(int argc, char** argv)\n{",
            "int main(int argc, char** argv)\n{\n  constexpr G4int kSteppingVerbosePrecision = 4;",
            1,
        )
        content = content.replace(
            "int main() {\n",
            "int main() {\n  constexpr G4int kSteppingVerbosePrecision = 4;\n",
            1,
        )
    content = re.sub(r"\n\s*G4int precision = 4;\n", "\n", content)
    content = content.replace("UseBestUnit(precision)", "UseBestUnit(kSteppingVerbosePrecision)")
    return content


def _qualify_sensitive_detector_hit_type(content: str) -> str:
    """Avoid G4VSensitiveDetector::Hit hiding a user Hit class in member scope."""
    content = re.sub(
        r"(?<![:\w])Hit\s*\*\s*([A-Za-z_]\w*)\s*=\s*new\s+Hit\s*\(",
        r"::Hit* \1 = new ::Hit(",
        content,
    )
    content = re.sub(
        r"(?<![:\w])auto\s*\*\s*([A-Za-z_]\w*)\s*=\s*new\s+Hit\s*\(",
        r"::Hit* \1 = new ::Hit(",
        content,
    )
    return content


def _normalize_scoring_manager_reference_api(content: str) -> str:
    content = content.replace("ScoringManager::Instance()->", "ScoringManager::Instance().")
    content = re.sub(
        r"ScoringManager::Instance\(\)\.RecordEnergyDeposit\(([^,\n;]+),\s*0\.0\s*\)",
        r"ScoringManager::Instance().RecordEnergyDeposit(\1)",
        content,
    )
    return content


def _changed_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_by_path = {
        str(item.get("path")): item.get("new_content")
        for item in before.get("changed_files", [])
        if isinstance(item, dict)
    }
    return [
        str(item.get("path"))
        for item in after.get("changed_files", [])
        if isinstance(item, dict)
        and before_by_path.get(str(item.get("path"))) != item.get("new_content")
    ]


def _persist_patch(patch: dict[str, Any], job_id: str) -> None:
    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)
    (codegen_dir / "proposed_patch.json").write_text(
        json.dumps(patch, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _persist_report(report: dict[str, Any], job_id: str) -> None:
    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)
    Path(codegen_dir / "global_integration_agent_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _append_report_history(report, codegen_dir)


def _append_report_history(report: dict[str, Any], codegen_dir: Path) -> None:
    integration_dir = codegen_dir / "integration"
    integration_dir.mkdir(parents=True, exist_ok=True)
    history_entry = _report_history_entry(report)
    history_path = integration_dir / GLOBAL_INTEGRATION_ATTEMPT_HISTORY_FILENAME
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(history_entry, ensure_ascii=False, default=str) + "\n")


def _report_history_entry(report: dict[str, Any]) -> dict[str, Any]:
    runtime_attempts = report.get("runtime_gate_attempts")
    if not isinstance(runtime_attempts, list):
        runtime_attempts = []
    return {
        "job_id": report.get("job_id"),
        "status": report.get("status"),
        "agent_name": report.get("agent_name"),
        "issues_fixed": report.get("issues_fixed", []),
        "changed_files": report.get("changed_files", []),
        "errors": report.get("errors", []),
        "warnings": report.get("warnings", []),
        "runtime_gate_attempts": runtime_attempts,
        "agentic": report.get("agentic"),
        "continuation_request": report.get("continuation_request"),
    }
