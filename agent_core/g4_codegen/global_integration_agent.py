"""High-privilege global integration agent for assembled Geant4 modules.

This is the only cross-module writer in the codegen flow. It receives all
module outputs, reads the assembled project files,
collects local RAG and web-search evidence, and returns a schema-preserving
proposed_patch for the complete Geant4 program.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir
from agent_core.models.gateway import _safe_parse_json, get_model_gateway
from agent_core.models.schemas import ModelProvider, ModelTask, ModelTier

GLOBAL_INTEGRATION_SYSTEM_PROMPT = """你是 RadAgent 的全局 Geant4 集成 Agent。

你在所有模块 Agent 完成后工作。你可以读取完整项目文件、模块契约、模块 gate 结果、
本地数据库检索结果和互联网搜索结果，并通过返回 proposed_patch 修改生成工程文件。

目标：把各模块拼成一个能编译、能运行、能产出约定 artifact 的完整 Geant4 程序。

硬性边界：
1. 只能返回 JSON，不得输出 Markdown fence。
2. 不得删除、简化或空实现模块原本承担的物理/几何/输出职责。
3. 可以修改任意 generated project file 来对齐接口、构造函数、include、CMake 和 main wiring。
4. 新增 adapter/wrapper 可以，但必须保留模块语义，且必须写入 issues_fixed。
5. 不得引入 content 字段；文件内容只能放在 new_content。
6. path 必须相对 08_geant4 根目录，不得以 08_geant4/ 开头。
7. 不确定的 Geant4 API 必须依据 database_search 或 web_search 证据；没有证据不要发明 API。
8. 不要把编译、运行或 artifact 失败隐藏成 warning。

返回格式：
{
  "status": "integrated" | "no_change" | "failed",
  "proposed_patch": {"changed_files": [...]},
  "issues_fixed": [{"target": "...", "message": "..."}],
  "errors": []
}
"""


async def run_global_integration_agent(
    proposed_patch: dict[str, Any],
    *,
    job_id: str,
    module_results: dict[str, Any] | None = None,
    module_gate_results: dict[str, Any] | None = None,
    module_contracts: dict[str, Any] | None = None,
    module_contexts: dict[str, Any] | None = None,
    interface_contracts: dict[str, Any] | None = None,
    runtime_failure_context: dict[str, Any] | None = None,
    static_semantic_scan: dict[str, Any] | None = None,
    cross_file_hard_gate: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the final global integration agent over module-generated files."""
    original_patch = deepcopy(proposed_patch or {})
    report: dict[str, Any] = {
        "job_id": job_id,
        "status": "passed",
        "agent_name": "global_integration_agent",
        "issues_fixed": [],
        "changed_files": [],
        "errors": [],
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
        "module_contracts": module_contracts or {},
        "module_context_summaries": _summarize_module_contexts(module_contexts or {}),
        "module_gate_results": module_gate_results or {},
        "interface_contracts": interface_contracts or {},
        "runtime_failure_context": runtime_failure_context or {},
        "static_semantic_scan": static_semantic_scan or {},
        "cross_file_hard_gate": cross_file_hard_gate or {},
        "integration_memory": _load_integration_memory(job_id),
        "project_files": _project_files_from_patch(original_patch),
        "write_contract": {
            "output": "proposed_patch JSON",
            "allowed_paths": "only generated project paths inside 08_geant4",
            "must_preserve_schema": True,
            "partial_response_merge": True,
            "final_runtime_gate": (
                "After patch application, gate_subgraph must pass Geant4 build, "
                "ctest, data contract, and smoke simulation gates."
            ),
        },
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
    report["evidence_path"] = "06_codegen/integration/global_integration_evidence.json"
    _persist_integration_context(integration_context, job_id)

    gateway = get_model_gateway()
    if _is_mock_gateway(gateway):
        original_patch.setdefault("metadata", {})
        original_patch["metadata"]["global_integration_agent"] = {
            "status": "no_change",
            "mock_provider_only": True,
            "report_path": "06_codegen/global_integration_agent_report.json",
            "runtime_gate_required": True,
        }
        report["llm_status"] = "no_change"
        report["mock_provider_only"] = True
        _persist_patch(original_patch, job_id)
        _persist_report(report, job_id)
        return original_patch, report

    if not _has_evidence(evidence):
        report["status"] = "failed"
        report["errors"].append(
            "Global integration requires local database or web-search evidence, "
            "but no evidence was available."
        )
        _persist_report(report, job_id)
        return original_patch, report

    result = await gateway.call(
        task=ModelTask.CODEGEN,
        tier=ModelTier.MAX,
        system_prompt=GLOBAL_INTEGRATION_SYSTEM_PROMPT,
        user_prompt=(
            "请读取 integration_context 中的 project_files、模块契约、gate 结果、"
            "database_search 和 web_search，然后返回最终 proposed_patch：\n"
            f"{json.dumps(integration_context, indent=2, ensure_ascii=False)[:65000]}"
        ),
        response_format="json",
        max_tokens=65536,
        metadata={
            "job_id": job_id,
            "module_name": "global_integration_agent",
            "available_modules": integration_context["available_modules"],
        },
    )
    if result.error:
        report["status"] = "failed"
        report["errors"].append(f"Global integration model call failed: {result.error}")
        _persist_report(report, job_id)
        return original_patch, report

    data = result.parsed_json or _safe_parse_json(result.content) or {}
    if not isinstance(data, dict):
        report["status"] = "failed"
        report["errors"].append("Global integration returned invalid JSON")
        _persist_report(report, job_id)
        return original_patch, report

    status = str(data.get("status", "")).strip().lower()
    if status == "repaired":
        status = "integrated"
    if status not in {"integrated", "no_change"}:
        report["status"] = "failed"
        report["errors"].append(f"Global integration returned status '{status or 'missing'}'")
        _persist_report(report, job_id)
        return original_patch, report

    candidate_patch = data.get("proposed_patch")
    if not isinstance(candidate_patch, dict):
        report["status"] = "failed"
        report["errors"].append("Global integration response missing proposed_patch object")
        _persist_report(report, job_id)
        return original_patch, report

    schema_errors = _validate_candidate_patch_schema(original_patch, candidate_patch)
    if schema_errors:
        report["status"] = "failed"
        report["errors"].extend(schema_errors)
        _persist_report(report, job_id)
        return original_patch, report

    integrated_patch, merge_errors = _merge_patch_by_path(original_patch, candidate_patch)
    if merge_errors:
        report["status"] = "failed"
        report["errors"].extend(merge_errors)
        _persist_report(report, job_id)
        return original_patch, report

    schema_errors = _validate_patch_schema(integrated_patch)
    if schema_errors:
        report["status"] = "failed"
        report["errors"].extend(schema_errors)
        _persist_report(report, job_id)
        return original_patch, report

    issues_fixed = data.get("issues_fixed", [])
    if isinstance(issues_fixed, list):
        report["issues_fixed"] = [
            issue
            for issue in issues_fixed
            if isinstance(issue, dict) and issue.get("target") and issue.get("message")
        ]
    report["changed_files"] = _changed_paths(original_patch, integrated_patch)
    report["llm_status"] = status

    integrated_patch.setdefault("metadata", {})
    integrated_patch["metadata"]["global_integration_agent"] = {
        "status": status,
        "issues_fixed": len(report["issues_fixed"]),
        "changed_files": len(report["changed_files"]),
        "report_path": "06_codegen/global_integration_agent_report.json",
        "runtime_gate_required": True,
    }
    integrated_patch["metadata"]["final_runtime_gate"] = {
        "required": True,
        "gates": ["Build/Parse", "Unit Test", "Data Contract", "Smoke Simulation"],
        "runner": "Geant4Runner.smoke_test",
    }

    _persist_patch(integrated_patch, job_id)
    _persist_report(report, job_id)
    return integrated_patch, report


def _is_mock_gateway(gateway: Any) -> bool:
    profile = getattr(gateway, "profiles", {}).get(ModelTier.MAX)
    return getattr(profile, "provider", None) == ModelProvider.MOCK


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
            "run_mode": context.get("run_mode", "strict"),
        }
    return summaries


def _load_integration_memory(job_id: str) -> dict[str, Any]:
    codegen_dir = get_job_dir(job_id) / "06_codegen"
    job_dir = get_job_dir(job_id)
    return {
        "previous_integration_report": _read_json_tail(
            codegen_dir / "global_integration_agent_report.json"
        ),
        "previous_integration_evidence": _read_json_tail(
            codegen_dir / "integration" / "global_integration_evidence.json"
        ),
        "previous_static_semantic_scan": _read_json_tail(
            codegen_dir / "static_semantic_scan.json"
        ),
        "previous_cross_file_hard_gate": _read_json_tail(
            codegen_dir / "cross_file_hard_gate.json"
        ),
        "previous_cross_file_llm_gate": _read_json_tail(
            codegen_dir / "cross_file_llm_gate.json"
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
    try:
        evidence["database_search"] = {
            "status": "pass",
            "results": await _search_database(query),
            "errors": [],
        }
        if not evidence["database_search"]["results"]:
            evidence["database_search"]["status"] = "empty"
    except Exception as exc:
        evidence["database_search"] = {"status": "error", "results": [], "errors": [str(exc)]}

    try:
        evidence["web_search"] = {
            "status": "pass",
            "results": await _search_web(query),
            "errors": [],
        }
        if not evidence["web_search"]["results"]:
            evidence["web_search"]["status"] = "empty"
    except Exception as exc:
        evidence["web_search"] = {"status": "error", "results": [], "errors": [str(exc)]}

    out_dir = get_job_dir(job_id) / "06_codegen" / "integration"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "global_integration_evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence["database_search"]["results"] = evidence["database_search"]["results"][:10]
    evidence["web_search"]["results"] = evidence["web_search"]["results"][:5]
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
    return " ".join(parts)[:1800]


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
    out_dir = get_job_dir(job_id) / "06_codegen" / "integration"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "global_integration_context.json").write_text(
        json.dumps(context, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _validate_patch_schema(patch: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    files = patch.get("changed_files")
    if not isinstance(files, list) or not files:
        return ["proposed_patch.changed_files must be a non-empty list"]
    for index, entry in enumerate(files):
        if not isinstance(entry, dict):
            errors.append(f"changed_files[{index}] must be an object")
            continue
        if "content" in entry:
            errors.append(f"{entry.get('path', index)}: content field is forbidden")
        for required in ("path", "new_content", "zone", "generated_by", "module_name"):
            if not entry.get(required):
                errors.append(f"{entry.get('path', index)}: missing {required}")
        path = str(entry.get("path", ""))
        if path.startswith("08_geant4/") or ".." in path or path.startswith("/"):
            errors.append(f"{path}: path must be relative to generated_code_dir")
        if "```" in str(entry.get("new_content", "")):
            errors.append(f"{path}: new_content must not contain markdown fences")
    return errors


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
        if path.startswith("08_geant4/") or ".." in path or path.startswith("/"):
            errors.append(f"{path}: path must be relative to generated_code_dir")
        if "```" in str(entry.get("new_content", "")):
            errors.append(f"{path}: new_content must not contain markdown fences")
        if path not in original_paths:
            for required in ("zone", "generated_by", "module_name"):
                if not entry.get(required):
                    errors.append(f"{path}: missing {required}")
    return errors


def _merge_patch_by_path(
    original_patch: dict[str, Any],
    candidate_patch: dict[str, Any],
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
            merged_files[original_by_path[path]] = merged_entry
        else:
            merged_files.append(deepcopy(entry))

    merged_patch = deepcopy(original_patch)
    merged_patch["changed_files"] = merged_files
    if isinstance(candidate_patch.get("metadata"), dict):
        metadata = deepcopy(original_patch.get("metadata", {}))
        if not isinstance(metadata, dict):
            metadata = {}
        metadata.update(deepcopy(candidate_patch["metadata"]))
        merged_patch["metadata"] = metadata
    return merged_patch, []


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
    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)
    (codegen_dir / "proposed_patch.json").write_text(
        json.dumps(patch, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _persist_report(report: dict[str, Any], job_id: str) -> None:
    codegen_dir = get_job_dir(job_id) / "06_codegen"
    codegen_dir.mkdir(parents=True, exist_ok=True)
    Path(codegen_dir / "global_integration_agent_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
