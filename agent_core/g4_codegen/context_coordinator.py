"""Context coordinator for generated Geant4 module code.

The coordinator is intentionally read-only. It summarizes code that earlier
module agents already wrote, builds a symbol/file index, and exposes a small
lookup surface for later agents to request exact snippets when summaries are
not enough.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent_core.observability import record_event
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import STAGE_CODEGEN

CONTEXT_COORDINATOR_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 代码上下文协调 Agent。

你不写代码，不修复代码，只阅读之前模块 agent 已生成的代码摘要，并产出给后续 agent 使用的协调摘要。

目标：
1. 汇总各模块暴露的真实 C++ 接口、构造函数、public methods、文件路径和关键符号。
2. 标出 runtime_app / global integration 最容易错配的边界：volume name、scoring/output API、
   action wiring、CMake source list、artifact contract。
3. 保持摘要紧凑；如果后续 agent 需要完整代码，它会通过 generated_code_lookup 工具读取。

只返回 JSON，不要 Markdown fence。

返回格式：
{
  "status": "ok",
  "module_summaries": {
    "module_name": {
      "role": "...",
      "files": ["include/X.hh"],
      "public_interfaces": ["Class::Method(args)"],
      "constructor_contracts": ["Class(args)"],
      "symbols": ["Class"],
      "integration_notes": ["..."],
      "risks": ["..."]
    }
  },
  "cross_module_contracts": [
    {"producer": "...", "consumer": "...", "contract": "...", "evidence": ["path"]}
  ],
  "runtime_contract_notes": ["..."],
  "recommended_code_reads": [
    {"path": "include/DetectorConstruction.hh", "reason": "confirm public signature"}
  ],
  "warnings": []
}
"""


async def coordinate_generated_context(
    *,
    job_id: str,
    module_results: dict[str, Any],
    module_contracts: dict[str, Any] | None = None,
    target_modules: list[str] | None = None,
    coordinator_name: str = "context_coordinator",
) -> dict[str, Any]:
    """Summarize generated code deterministically for later agents.

    Earlier versions sent the deterministic summaries back through a Lite model,
    but the prompt grew with generated C++ and added a slow non-essential call.
    The regex/file manifest already contains the API facts later agents need.
    """

    files = _collect_generated_files(module_results)
    deterministic = _deterministic_coordination(
        module_results=module_results,
        files=files,
        module_contracts=module_contracts or {},
        target_modules=target_modules or [],
    )
    _persist_coordination(job_id, coordinator_name, deterministic)
    return deterministic


def lookup_generated_code_snippets(
    requests: list[dict[str, Any]],
    *,
    job_id: str,
    module_results: dict[str, Any] | None = None,
    max_results: int = 8,
) -> dict[str, Any]:
    """Return exact generated-code snippets requested by a later agent."""

    files = _collect_generated_files(module_results or _load_persisted_module_results(job_id))
    snippets: list[dict[str, Any]] = []
    errors: list[str] = []
    for request in requests[:max_results]:
        path = str(request.get("path") or "").strip()
        symbol = str(request.get("symbol") or "").strip()
        query = str(request.get("query") or "").strip()
        max_chars = _positive_int(request.get("max_chars"), 8000)
        context_lines = _positive_int(request.get("context_lines"), 80)
        matches = _match_files(files, path=path, symbol=symbol, query=query)
        if not matches:
            errors.append(
                "No generated code matched "
                f"path={path or '*'} symbol={symbol or '*'} query={query or '*'}"
            )
            continue
        for file_entry in matches[:2]:
            snippet = _snippet_for_request(
                file_entry["content"],
                symbol=symbol,
                query=query,
                context_lines=context_lines,
                max_chars=max_chars,
            )
            snippets.append(
                {
                    "module_name": file_entry["module_name"],
                    "path": file_entry["path"],
                    "symbol": symbol,
                    "query": query,
                    "content": snippet,
                    "truncated": len(snippet) >= max_chars,
                }
            )
            if len(snippets) >= max_results:
                break
        if len(snippets) >= max_results:
            break
    return {
        "tool_name": "generated_code_lookup",
        "status": "ok" if snippets else "empty",
        "requests": requests[:max_results],
        "snippets": snippets,
        "errors": errors,
    }


def build_generated_code_lookup_manifest(module_results: dict[str, Any]) -> dict[str, Any]:
    files = _collect_generated_files(module_results)
    file_entries = []
    symbol_index: dict[str, list[dict[str, str]]] = {}
    for file_entry in files:
        summary = _summarize_file(
            file_entry["module_name"],
            file_entry["path"],
            file_entry["content"],
        )
        file_entries.append(
            {
                "module_name": file_entry["module_name"],
                "path": file_entry["path"],
                "byte_count": len(file_entry["content"].encode("utf-8", errors="ignore")),
                "classes": summary["classes"],
                "public_methods": summary["public_methods"],
                "constructor_signatures": summary["constructor_signatures"],
            }
        )
        for symbol in summary["classes"] + summary["public_methods"]:
            symbol_index.setdefault(symbol, []).append(
                {"module_name": file_entry["module_name"], "path": file_entry["path"]}
            )
    return {
        "tool_name": "generated_code_lookup",
        "status": "available" if files else "empty",
        "usage_rule": (
            "If summaries are insufficient, return status='needs_code_context' "
            "with code_context_requests. The system will provide exact snippets."
        ),
        "request_schema": {
            "path": "relative geant4_project path, e.g. include/DetectorConstruction.hh",
            "symbol": "optional class/function symbol",
            "query": "optional literal substring",
            "context_lines": "optional integer",
            "max_chars": "optional integer",
        },
        "files": file_entries,
        "symbol_index": symbol_index,
    }


def _deterministic_coordination(
    *,
    module_results: dict[str, Any],
    files: list[dict[str, str]],
    module_contracts: dict[str, Any],
    target_modules: list[str],
) -> dict[str, Any]:
    file_summaries = [
        _summarize_file(file_entry["module_name"], file_entry["path"], file_entry["content"])
        for file_entry in files
    ]
    module_summaries: dict[str, dict[str, Any]] = {}
    for module_name, result in module_results.items():
        module_files = [s for s in file_summaries if s["module_name"] == module_name]
        contract = module_contracts.get(module_name, {})
        module_summaries[module_name] = {
            "role": "; ".join(contract.get("responsibilities", [])[:3])
            if isinstance(contract, dict)
            else "",
            "files": [s["path"] for s in module_files],
            "public_interfaces": [
                method for summary in module_files for method in summary["public_methods"]
            ],
            "constructor_contracts": [
                sig for summary in module_files for sig in summary["constructor_signatures"]
            ],
            "symbols": [symbol for summary in module_files for symbol in summary["classes"]],
            "integration_notes": _module_integration_notes(module_name, module_files),
            "risks": [],
        }
    return {
        "status": "ok",
        "coordinator": "deterministic",
        "target_modules": target_modules,
        "module_summaries": module_summaries,
        "file_summaries": file_summaries,
        "generated_code_lookup_manifest": build_generated_code_lookup_manifest(module_results),
        "cross_module_contracts": [],
        "runtime_contract_notes": [
            "Generated runtime code must write g4_summary.json, provenance.json, "
            "event_table.csv, edep_3d.csv, and dose_3d.csv to G4_OUTPUT_DIR.",
            "Later agents should read exact headers before calling constructors or public methods.",
        ],
        "recommended_code_reads": _recommended_code_reads(file_summaries),
        "warnings": [],
    }


def _collect_generated_files(module_results: dict[str, Any]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for module_name, result in sorted(module_results.items()):
        if not isinstance(result, dict):
            continue
        for file_entry in result.get("generated_files", []):
            if not isinstance(file_entry, dict):
                continue
            path = str(file_entry.get("path") or "").strip()
            content = str(file_entry.get("new_content") or file_entry.get("content") or "")
            if not path or not content:
                continue
            files.append({"module_name": module_name, "path": path, "content": content})
    return files


def _load_persisted_module_results(job_id: str) -> dict[str, Any]:
    output_dir = get_job_dir(job_id) / STAGE_CODEGEN / "module_outputs"
    results: dict[str, Any] = {}
    if not output_dir.is_dir():
        return results
    for path in sorted(output_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            module_name = str(data.get("module_name") or path.stem)
            results[module_name] = data
    return results


def _summarize_file(module_name: str, path: str, content: str) -> dict[str, Any]:
    classes = re.findall(r"\bclass\s+([A-Za-z_]\w*)", content)
    public_methods = _extract_public_methods(content)
    constructors = _extract_constructor_signatures(content, classes)
    includes = re.findall(r'#include\s+[<"]([^>"]+)[>"]', content)
    return {
        "module_name": module_name,
        "path": path,
        "classes": sorted(set(classes)),
        "public_methods": public_methods,
        "constructor_signatures": constructors,
        "includes": sorted(set(includes)),
        "provided_symbols": sorted(set(classes + public_methods)),
    }


def _extract_public_methods(content: str) -> list[str]:
    methods: list[str] = []
    public_blocks = re.findall(
        r"\bpublic:\s*(.*?)(?=\bprivate:|\bprotected:|\n};|$)",
        content,
        re.DOTALL,
    )
    for block in public_blocks:
        for match in re.finditer(r"(?:~?[A-Za-z_]\w*|operator\s+\w+)\s*\(", block):
            name = match.group(0).split("(", 1)[0].strip()
            if name not in {"if", "for", "while", "switch", "return"}:
                methods.append(name)
    return sorted(set(methods))


def _extract_constructor_signatures(content: str, classes: list[str]) -> list[str]:
    signatures: list[str] = []
    public_blocks = re.findall(
        r"\bpublic:\s*(.*?)(?=\bprivate:|\bprotected:|\n};|$)",
        content,
        re.DOTALL,
    )
    for class_name in classes:
        pattern = (
            rf"(?:explicit\s+)?{re.escape(class_name)}\s*"
            r"\([^;{}]*\)\s*(?:=\s*default)?\s*;"
        )
        for block in public_blocks:
            for match in re.finditer(pattern, block, re.DOTALL):
                signatures.append(re.sub(r"\s+", " ", match.group(0)).strip().rstrip(";"))
    return sorted(set(signatures))


def _module_integration_notes(module_name: str, file_summaries: list[dict[str, Any]]) -> list[str]:
    paths = {summary["path"] for summary in file_summaries}
    notes: list[str] = []
    if module_name == "simulation_core":
        notes.append(
            "runtime_app must read DetectorConstruction and scoring/sensitive detector "
            "headers before wiring actions."
        )
    if module_name == "beam_physics":
        notes.append(
            "runtime_app/global integration must call the physics factory return value, "
            "not the wrapper object."
        )
    if "include/OutputManager.hh" in paths:
        notes.append(
            "OutputManager public API is the source of truth for action wiring and "
            "artifact output."
        )
    return notes


def _recommended_code_reads(file_summaries: list[dict[str, Any]]) -> list[dict[str, str]]:
    preferred = {
        "include/DetectorConstruction.hh": "confirm detector public API and scoring volume names",
        "include/OutputManager.hh": "confirm output/action-facing API",
        "include/ScoringManager.hh": "confirm scoring API before writing runtime actions",
        "include/PhysicsListFactoryWrapper.hh": "confirm physics-list factory ownership",
        "include/PrimaryGeneratorAction.hh": "confirm source constructor and action API",
    }
    available = {summary["path"] for summary in file_summaries}
    return [
        {"path": path, "reason": reason}
        for path, reason in preferred.items()
        if path in available
    ]


def _match_files(
    files: list[dict[str, str]],
    *,
    path: str,
    symbol: str,
    query: str,
) -> list[dict[str, str]]:
    matches = files
    if path:
        matches = [file_entry for file_entry in matches if file_entry["path"] == path]
    if symbol:
        matches = [
            file_entry
            for file_entry in matches
            if symbol in file_entry["content"] or symbol in Path(file_entry["path"]).stem
        ]
    if query:
        matches = [file_entry for file_entry in matches if query in file_entry["content"]]
    return matches


def _snippet_for_request(
    content: str,
    *,
    symbol: str,
    query: str,
    context_lines: int,
    max_chars: int,
) -> str:
    if not symbol and not query:
        return content[:max_chars]
    lines = content.splitlines()
    needle = symbol or query
    index = next((i for i, line in enumerate(lines) if needle in line), None)
    if index is None:
        return content[:max_chars]
    start = max(0, index - context_lines)
    end = min(len(lines), index + context_lines + 1)
    snippet = "\n".join(lines[start:end])
    return snippet[:max_chars]


def _persist_coordination(job_id: str, coordinator_name: str, data: dict[str, Any]) -> None:
    out_dir = get_job_dir(job_id) / STAGE_CODEGEN / "context_coordination"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{coordinator_name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    record_event(
        job_id=job_id,
        event_type="context_coordination",
        status="passed" if data.get("status") in {"ok", "pass", "passed"} else "failed",
        phase="g4_codegen",
        module_name=coordinator_name,
        summary=f"{coordinator_name} generated context summary",
        metrics={
            "module_count": len(data.get("module_summaries", {})),
            "file_count": len(data.get("file_summaries", [])),
        },
        artifacts=[{"path": str(path)}],
        warnings=_string_list(data.get("warnings", [])),
    )


def _trim_jsonable(value: Any, max_chars: int) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= max_chars:
        return value
    return {"summary": text[: max_chars - 40] + "\n[truncated]"}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
