"""Global LLM repair pass for assembled Geant4 patches.

This pass runs before the deterministic global normalizer. It gives a model
the complete assembled patch plus any runtime failure context, and requires a
schema-preserving proposed_patch response.
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent_core.config.workspace import get_job_dir
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelProvider, ModelTask, ModelTier

GLOBAL_LLM_REPAIR_SYSTEM_PROMPT = """你是 RadAgent 的全局 Geant4 代码修复 Agent。

你负责在所有模块代码 assemble 完成后，进行跨文件、跨模块、真实编译导向的修复。

必须遵守：
1. 你必须返回 JSON，不得输出 Markdown fence。
2. 你应该返回完整 proposed_patch，不能返回 diff 格式；如果只返回被修改文件，
   系统会按 path 覆盖回原始全量 patch，未返回文件必须视为保持不变。
3. proposed_patch.changed_files 每个文件必须保留 path、operation、new_content、zone、
   generated_by、module_name、rationale。
4. 不得引入 content 字段。
5. 不得删除无关模块文件。
6. 修复方向必须是让代码通过真实 Geant4 编译、运行、gate 和 artifact 检查。
7. 如果 runtime_failure_context 中有编译/运行/gate 错误，优先修复这些错误。
8. 不确定的 Geant4 API 不要发明；使用已有 RAG/web 证据、模块上下文和代码中已存在接口。
9. 不要把错误隐藏到注释、空实现或跳过逻辑中。
10. 不要把真实失败改成 warning。
11. 不要修改 patch 外路径，不要生成 08_geant4/ 前缀路径。
12. 必须先根据 repair_context.failure_context 判断失败类型：
    compile_error、runtime_error、artifact_error、gate_error 或 integration_error。
13. 必须阅读 repair_context.project_files 中所有相关文件，理解跨文件接口后再修改。
14. 必须阅读 repair_context.retrieval_context 中的 RAG/web 证据；
    如果证据为空且涉及 Geant4 API，返回 failed，不要凭空编造 API。
15. 修改必须最小化但完整：修复根因，同时保持所有模块契约和文件边界。
16. 不要输出思维链；只在 issues_fixed 中给出简短、可审计的修复理由。

必须返回：
{
  "status": "repaired" | "no_change" | "failed",
  "proposed_patch": {"changed_files": [...]},
  "issues_fixed": [{"target": "...", "message": "..."}],
  "errors": []
}
"""


async def run_global_llm_repair(
    proposed_patch: dict[str, Any],
    *,
    job_id: str,
    runtime_failure_context: dict[str, Any] | None = None,
    module_gate_results: dict[str, Any] | None = None,
    static_semantic_scan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run a schema-preserving global LLM repair over an assembled patch."""
    original_patch = deepcopy(proposed_patch or {})
    report: dict[str, Any] = {
        "job_id": job_id,
        "status": "passed",
        "agent_name": "global_llm_repair_agent",
        "issues_fixed": [],
        "changed_files": [],
        "errors": [],
    }

    changed_files = original_patch.get("changed_files", [])
    if not isinstance(changed_files, list) or not changed_files:
        report["status"] = "failed"
        report["errors"].append("proposed_patch.changed_files is empty")
        _persist_report(report, job_id)
        return original_patch, report

    failure_context = runtime_failure_context or {}
    retrieval_context = await _collect_global_repair_evidence(
        job_id=job_id,
        proposed_patch=original_patch,
        runtime_failure_context=failure_context,
    )
    project_files = _project_files_from_patch(original_patch)

    repair_context = {
        "job_id": job_id,
        "failure_context": _classify_failure_context(failure_context),
        "proposed_patch": original_patch,
        "project_files": project_files,
        "runtime_failure_context": runtime_failure_context or {},
        "module_gate_results": module_gate_results or {},
        "static_semantic_scan": static_semantic_scan or {},
        "retrieval_context": retrieval_context,
        "global_repair_policy": {
            "sequence": "global_llm_repair first, deterministic global normalizer second",
            "must_preserve_patch_schema": True,
            "must_not_add_content_field": True,
            "must_not_prefix_paths_with_08_geant4": True,
            "model_may_modify_any_project_file_in_changed_files": True,
            "disk_write_path": "only through returned proposed_patch",
        },
    }

    gateway = get_model_gateway()
    if _is_mock_gateway(gateway):
        report["llm_status"] = "no_change"
        report["mock_provider_only"] = True
        report["retrieval_context_path"] = "06_codegen/repair/global_llm_repair_evidence.json"
        original_patch.setdefault("metadata", {})
        original_patch["metadata"]["global_llm_repair"] = {
            "status": "no_change",
            "mock_provider_only": True,
            "report_path": "06_codegen/global_llm_repair_report.json",
        }
        _persist_patch(original_patch, job_id)
        _persist_report(report, job_id)
        return original_patch, report

    if _requires_external_evidence(failure_context) and not _has_repair_evidence(
        retrieval_context
    ):
        report["status"] = "failed"
        report["errors"].append(
            "Global LLM repair requires RAG/web evidence for Geant4 API or runtime "
            "failure repair, but no evidence was retrieved."
        )
        _persist_report(report, job_id)
        return original_patch, report

    result = await gateway.call(
        task=ModelTask.FAILURE_DIAGNOSIS,
        tier=ModelTier.MAX,
        system_prompt=GLOBAL_LLM_REPAIR_SYSTEM_PROMPT,
        user_prompt=(
            "请执行全局代码修复，并严格按 system prompt 的 JSON schema 返回：\n"
            f"{json.dumps(repair_context, indent=2, ensure_ascii=False)[:60000]}"
        ),
        response_format="json",
        max_tokens=65536,
        metadata={
            "job_id": job_id,
            "module_name": "global_llm_repair",
            "repair_scope": "global",
        },
    )

    if result.error:
        report["status"] = "failed"
        report["errors"].append(f"Global LLM repair call failed: {result.error}")
        _persist_report(report, job_id)
        return original_patch, report

    try:
        data = result.parsed_json or json.loads(result.content.strip())
    except Exception as exc:
        report["status"] = "failed"
        report["errors"].append(f"Global LLM repair returned invalid JSON: {exc}")
        _persist_report(report, job_id)
        return original_patch, report

    status = str(data.get("status", "")).strip().lower()
    if status not in {"repaired", "no_change"}:
        report["status"] = "failed"
        report["errors"].append(f"Global LLM repair returned status '{status or 'missing'}'")
        _persist_report(report, job_id)
        return original_patch, report

    repaired_patch = data.get("proposed_patch")
    if not isinstance(repaired_patch, dict):
        report["status"] = "failed"
        report["errors"].append("Global LLM repair response missing proposed_patch object")
        _persist_report(report, job_id)
        return original_patch, report

    validation_errors = _validate_patch_schema(repaired_patch)
    if validation_errors:
        report["status"] = "failed"
        report["errors"].extend(validation_errors)
        _persist_report(report, job_id)
        return original_patch, report

    repaired_patch, merge_errors = _merge_repaired_patch(original_patch, repaired_patch)
    if merge_errors:
        report["status"] = "failed"
        report["errors"].extend(merge_errors)
        _persist_report(report, job_id)
        return original_patch, report

    validation_errors = _validate_patch_schema(repaired_patch)
    if validation_errors:
        report["status"] = "failed"
        report["errors"].extend(validation_errors)
        _persist_report(report, job_id)
        return original_patch, report

    issues_fixed = data.get("issues_fixed", [])
    if not isinstance(issues_fixed, list):
        issues_fixed = []

    report["issues_fixed"] = [
        issue
        for issue in issues_fixed
        if isinstance(issue, dict) and issue.get("target") and issue.get("message")
    ]
    report["changed_files"] = _changed_paths(original_patch, repaired_patch)
    report["llm_status"] = status
    report["retrieval_context_path"] = "06_codegen/repair/global_llm_repair_evidence.json"

    repaired_patch.setdefault("metadata", {})
    repaired_patch["metadata"]["global_llm_repair"] = {
        "status": status,
        "issues_fixed": len(report["issues_fixed"]),
        "report_path": "06_codegen/global_llm_repair_report.json",
    }

    _persist_patch(repaired_patch, job_id)
    _persist_report(report, job_id)
    return repaired_patch, report


def _is_mock_gateway(gateway: Any) -> bool:
    profile = getattr(gateway, "profiles", {}).get(ModelTier.MAX)
    return getattr(profile, "provider", None) == ModelProvider.MOCK


def _requires_external_evidence(runtime_failure_context: dict[str, Any]) -> bool:
    if runtime_failure_context:
        return True
    return True


def _has_repair_evidence(retrieval_context: dict[str, Any]) -> bool:
    rag_results = retrieval_context.get("rag", {}).get("results", [])
    web_results = retrieval_context.get("web", {}).get("results", [])
    return bool(rag_results or web_results)


async def _collect_global_repair_evidence(
    *,
    job_id: str,
    proposed_patch: dict[str, Any],
    runtime_failure_context: dict[str, Any],
) -> dict[str, Any]:
    query = _build_global_repair_query(proposed_patch, runtime_failure_context)
    evidence: dict[str, Any] = {
        "query": query,
        "rag": {"status": "not_run", "results": [], "errors": []},
        "web": {"status": "not_run", "results": [], "errors": []},
        "policy": {
            "required_for_geant4_api_repairs": True,
            "use": "Use retrieved Geant4 API evidence before changing API calls.",
        },
    }
    try:
        evidence["rag"] = {
            "status": "pass",
            "results": await _search_global_repair_rag(query),
            "errors": [],
        }
        if not evidence["rag"]["results"]:
            evidence["rag"]["status"] = "empty"
    except Exception as exc:
        evidence["rag"] = {"status": "error", "results": [], "errors": [str(exc)]}

    try:
        evidence["web"] = {
            "status": "pass",
            "results": await _search_global_repair_web(query),
            "errors": [],
        }
        if not evidence["web"]["results"]:
            evidence["web"]["status"] = "empty"
    except Exception as exc:
        evidence["web"] = {"status": "error", "results": [], "errors": [str(exc)]}

    repair_dir = get_job_dir(job_id) / "06_codegen" / "repair"
    repair_dir.mkdir(parents=True, exist_ok=True)
    (repair_dir / "global_llm_repair_evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    evidence["rag"]["results"] = evidence["rag"]["results"][:8]
    evidence["web"]["results"] = evidence["web"]["results"][:5]
    return evidence


def _build_global_repair_query(
    proposed_patch: dict[str, Any],
    runtime_failure_context: dict[str, Any],
) -> str:
    text_parts: list[str] = ["Geant4 global repair compile runtime gate artifact"]
    for key in ("errors", "warnings", "failed_gates", "build_errors", "runtime_errors"):
        value = runtime_failure_context.get(key)
        if isinstance(value, list):
            text_parts.extend(str(item) for item in value[:8])
        elif isinstance(value, str):
            text_parts.append(value)
    for item in proposed_patch.get("changed_files", []):
        if not isinstance(item, dict):
            continue
        content = str(item.get("new_content", ""))
        for token in (
            "G4Exception",
            "G4ExceptionDescription",
            "G4VScoringMesh",
            "GetScoreMap",
            "G4LogicalVolume",
            "G4THitsCollection",
            "G4Allocator",
            "G4_OUTPUT_DIR",
        ):
            if token in content:
                text_parts.append(token)
    return " ".join(text_parts)[:1600]


async def _search_global_repair_rag(query: str) -> list[dict[str, Any]]:
    from agent_core.context.nodes import _ensure_indexed, _get_rag_client

    client = _get_rag_client()
    if not await client.backend_available():
        return []
    if not await _ensure_indexed(client):
        return []
    results = await client.search(query, top_k=10, min_score=0.0)
    return [
        {
            "doc_id": result.doc_id,
            "title": result.title,
            "content": result.content[:1400],
            "source": result.source,
            "score": round(result.score, 4),
        }
        for result in results
    ]


async def _search_global_repair_web(query: str) -> list[dict[str, Any]]:
    from agent_core.tools.web_search_tool import WebSearchTool

    tool = WebSearchTool()
    if not tool.search_available:
        return []
    results = await tool.search(query, max_results=5)
    return [
        {
            "title": result.title,
            "url": result.url,
            "snippet": result.snippet[:800],
            "source_type": result.source_type,
            "confidence": result.confidence,
        }
        for result in results
    ]


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


def _classify_failure_context(runtime_failure_context: dict[str, Any]) -> dict[str, Any]:
    combined = json.dumps(runtime_failure_context, ensure_ascii=False)
    failure_types: list[str] = []
    if any(token in combined for token in ("error:", "Build failed", "cmake", "gmake")):
        failure_types.append("compile_error")
    if any(token in combined for token in ("Smoke simulation", "runtime", "segmentation", "Run")):
        failure_types.append("runtime_error")
    if any(token in combined for token in ("Missing:", "artifact", "output.csv", "g4_summary")):
        failure_types.append("artifact_error")
    if any(token in combined for token in ("Gate", "magic number", "validation")):
        failure_types.append("gate_error")
    if not failure_types:
        failure_types.append("integration_review")
    return {
        "types": sorted(set(failure_types)),
        "requires_rag": True,
        "requires_full_patch_review": True,
    }


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
        if path.startswith("08_geant4/"):
            errors.append(f"{path}: path must be relative to generated_code_dir")
        if "```" in str(entry.get("new_content", "")):
            errors.append(f"{path}: new_content must not contain markdown fences")
    return errors


def _merge_repaired_patch(
    original_patch: dict[str, Any],
    repaired_patch: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Overlay LLM-edited files onto the original full patch without dropping modules."""
    original_files = original_patch.get("changed_files")
    repaired_files = repaired_patch.get("changed_files")
    if not isinstance(original_files, list) or not original_files:
        return original_patch, ["original proposed_patch.changed_files is empty"]
    if not isinstance(repaired_files, list) or not repaired_files:
        return original_patch, ["repaired proposed_patch.changed_files is empty"]

    original_paths: list[str] = []
    original_by_path: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, entry in enumerate(original_files):
        if not isinstance(entry, dict):
            return original_patch, [f"original changed_files[{index}] must be an object"]
        path = str(entry.get("path", ""))
        if not path:
            return original_patch, [f"original changed_files[{index}] missing path"]
        if path in original_by_path:
            return original_patch, [f"original proposed_patch has duplicate path: {path}"]
        original_paths.append(path)
        original_by_path[path] = (index, deepcopy(entry))

    merged_files = [deepcopy(entry) for entry in original_files]
    seen_repaired_paths: set[str] = set()
    for index, entry in enumerate(repaired_files):
        if not isinstance(entry, dict):
            return original_patch, [f"repaired changed_files[{index}] must be an object"]
        path = str(entry.get("path", ""))
        if not path:
            return original_patch, [f"repaired changed_files[{index}] missing path"]
        if path in seen_repaired_paths:
            return original_patch, [f"repaired proposed_patch has duplicate path: {path}"]
        seen_repaired_paths.add(path)
        if path in original_by_path:
            original_index = original_by_path[path][0]
            merged_files[original_index] = deepcopy(entry)
        else:
            merged_files.append(deepcopy(entry))

    merged_patch = deepcopy(original_patch)
    merged_patch["changed_files"] = merged_files
    if isinstance(repaired_patch.get("metadata"), dict):
        merged_metadata = deepcopy(original_patch.get("metadata", {}))
        if not isinstance(merged_metadata, dict):
            merged_metadata = {}
        merged_metadata.update(deepcopy(repaired_patch["metadata"]))
        merged_patch["metadata"] = merged_metadata

    merged_paths = {
        str(entry.get("path"))
        for entry in merged_patch.get("changed_files", [])
        if isinstance(entry, dict)
    }
    missing_paths = [path for path in original_paths if path not in merged_paths]
    if missing_paths:
        return original_patch, [
            "Global LLM repair dropped original patch files: "
            + ", ".join(missing_paths[:20])
        ]
    return merged_patch, []


def _changed_paths(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_by_path = {
        str(item.get("path")): item.get("new_content")
        for item in before.get("changed_files", [])
        if isinstance(item, dict)
    }
    changed: list[str] = []
    for item in after.get("changed_files", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path"))
        if before_by_path.get(path) != item.get("new_content"):
            changed.append(path)
    return changed


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
    Path(codegen_dir / "global_llm_repair_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
