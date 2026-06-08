"""Base class and utilities for module agents."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier

logger = logging.getLogger(__name__)

MODULE_CODEGEN_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 C++ 模块级编码 Agent。

你不是模板填空器。
你只负责当前模块。
你必须根据 ModuleContract、ModuleContext、G4ModelIR 子集、
规则、RAG 参考片段和 Geant4 API 约束，
生成当前模块需要的完整文件内容。
ModuleContext 中的 module_code_example 是当前模块风格和接口示例，
interface_context 是上下游模块接口边界，
context_retrieval_policy 规定信息不足时如何使用 RAG 和 web 证据。

严格要求：
1. 只生成当前模块负责的文件。
2. 不要生成整个工程。
3. 每个文件必须是完整文件内容。
4. 不得输出 Markdown fence。
5. 不得出现空 include。
6. 不得出现 TODO、NotImplemented、stub、dummy、PLACEHOLDER。
7. 不得使用未带类型的 std::map。
8. 不得实例化 Geant4 抽象基类。
9. 使用单位时必须 include G4SystemOfUnits.hh。
10. 不得把 unsupported geometry 简化成 G4Box。
11. 不得伪造 CAD/GDML 转换。
12. 不得伪造 TCAD/SPICE 结果。
13. 必须说明 rationale、dependencies、satisfies、risk_notes、used_references。
14. 输出 JSON，不要输出额外文字。
15. generated_files 中每个文件对象必须使用字段 path 和 new_content。
16. 每个文件对象的路径字段固定为 path。
17. 每个文件对象的完整文件内容字段固定为 new_content。
18. JSON 顶层必须包含 generated_files 数组。
19. generated_files 数组必须包含完整可写入文件，不是文件摘要、计划或说明。
20. 必须遵守 module_code_example 的 owned_files 和 primary_symbols；示例只用于接口形状，
    不能照抄成占位实现。
21. 生成代码前先检查 interface_context 和 existing_generated_file_summaries；
    调用上游模块时必须匹配其真实类名、构造函数和 public 方法。
22. 如果 Geant4 API、宏命令、ownership、构造函数或 scoring 访问方式不确定，
    必须优先使用 rag_snippets；RAG 不足时使用 web_context 中的可信 Geant4/CERN 来源。
23. 使用 RAG 或 web 得到的 API 事实必须写入 used_references；没有证据不得发明 API。

返回格式：
{
  "module_name": "...",
  "status": "generated",
  "generated_files": [
    {
      "path": "08_geant4/include/XXX.hh",
      "operation": "create_or_replace",
      "new_content": "完整文件内容",
      "generated_by": "xxx_module_agent",
      "module_name": "xxx",
      "rationale": "...",
      "dependencies": [],
      "satisfies": [],
      "risk_notes": [],
      "used_references": []
    }
  ],
  "warnings": [],
  "errors": []
}
"""


async def run_module_agent(
    module_name: str,
    module_context: dict[str, Any],
    system_prompt: str = MODULE_CODEGEN_SYSTEM_PROMPT,
) -> ModuleAgentResult:
    """Run a module agent to generate code for a single module.

    This is the standard entry point for all module agents.
    Uses ModelGateway with CODEGEN task and PRO tier.
    """
    gateway = get_model_gateway()
    job_id = (
        module_context.get("job_id")
        or module_context.get("g4_model_ir_subset", {}).get("job_id")
        or module_context.get("codegen_plan", {}).get("job_id")
        or ""
    )

    effective_system_prompt = (
        system_prompt
        if system_prompt == MODULE_CODEGEN_SYSTEM_PROMPT
        else f"{MODULE_CODEGEN_SYSTEM_PROMPT}\n\n模块专用要求：\n{system_prompt}"
    )

    user_prompt = f"""模块上下文：
{json.dumps(module_context, indent=2, ensure_ascii=False)}

请根据 ModuleContract 和 ModuleContext 生成当前模块的完整文件内容。
输出 JSON，不要输出额外文字。
JSON 顶层必须直接包含 module_name、status、generated_files、warnings、errors。
不得输出 {{"{module_name}": ...}} 这种按模块名包裹的嵌套对象。"""

    result = await gateway.call(
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt=effective_system_prompt,
        user_prompt=user_prompt,
        response_format="json",
        max_tokens=65536,
        metadata={"module_name": module_name, "job_id": job_id},
    )

    if result.error:
        return ModuleAgentResult(
            module_name=module_name,
            status="failed",
            generated_files=[],
            errors=[f"Model call failed: {result.error}"],
        )

    # Parse response
    try:
        data = result.parsed_json or json.loads(result.content.strip())
    except (json.JSONDecodeError, TypeError) as exc:
        return ModuleAgentResult(
            module_name=module_name,
            status="failed",
            generated_files=[],
            errors=[f"Invalid JSON response: {exc}"],
        )

    # Build result
    generated_files: list[GeneratedModuleFile] = []
    parse_errors: list[str] = []
    file_entries = _extract_generated_file_entries(data)
    for f in file_entries:
        try:
            if not isinstance(f, dict):
                raise TypeError(f"file entry must be object, got {type(f).__name__}")
            new_content = f.get("new_content", f.get("content"))
            if new_content is None:
                raise KeyError("new_content")
            path = f.get(
                "path",
                f.get("file_path", f.get("filepath", f.get("filename", f.get("name")))),
            )
            if path is None:
                raise KeyError("path")
            path = _normalize_generated_path(module_name, path)
            generated_files.append(
                GeneratedModuleFile(
                    path=path,
                    operation=f.get("operation", "create_or_replace"),
                    new_content=new_content,
                    generated_by=f.get("generated_by", f"{module_name}_module_agent"),
                    module_name=f.get("module_name", module_name),
                    rationale=f.get("rationale", ""),
                    dependencies=f.get("dependencies", []),
                    satisfies=f.get("satisfies", []),
                    risk_notes=f.get("risk_notes", []),
                    used_references=f.get("used_references", []),
                )
            )
        except (KeyError, TypeError) as exc:
            keys = sorted(f.keys()) if isinstance(f, dict) else type(f).__name__
            message = f"Skipping invalid file entry with keys={keys}: {exc}"
            parse_errors.append(message)
            logger.warning(message)

    status = _normalize_module_status(data.get("status", "generated"))
    errors = list(data.get("errors", [])) + parse_errors
    if status in {"generated", "repaired"} and not generated_files:
        status = "failed"
        top_level_keys = sorted(data.keys()) if isinstance(data, dict) else type(data).__name__
        errors.append(
            "Model response did not contain any valid generated_files entries; "
            f"top_level_keys={top_level_keys}"
        )

    return ModuleAgentResult(
        module_name=module_name,
        status=status,
        generated_files=generated_files,
        errors=errors,
        warnings=data.get("warnings", []),
    )


def _normalize_module_status(value: Any) -> str:
    status = str(value or "generated").strip().lower()
    if status in {"generated", "success", "succeeded", "ok", "pass", "passed"}:
        return "generated"
    if status in {"repaired", "repair_success"}:
        return "repaired"
    return "failed"


def _extract_generated_file_entries(data: Any) -> list[Any]:
    """Return generated file entries from common real-provider JSON shapes."""
    if not isinstance(data, dict):
        return []
    for key in ("generated_files", "files", "repaired_files", "changed_files"):
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            entries = _extract_generated_file_entries(value)
            if entries:
                return entries
    for key in ("result", "output", "data"):
        nested = data.get(key)
        if isinstance(nested, dict):
            entries = _extract_generated_file_entries(nested)
            if entries:
                return entries
    path_keyed_entries: list[dict[str, Any]] = []
    for key, value in data.items():
        if not _looks_like_generated_file_path(key):
            continue
        if isinstance(value, dict):
            entry = dict(value)
            entry.setdefault("path", key)
        elif isinstance(value, str):
            entry = {"path": key, "new_content": value}
        else:
            continue
        path_keyed_entries.append(entry)
    if path_keyed_entries:
        return path_keyed_entries
    return []


def _looks_like_generated_file_path(value: str) -> bool:
    return (
        "/" in value
        or value in {"CMakeLists.txt", "main.cc"}
        or value.endswith((".cc", ".hh", ".hpp", ".h", ".mac", ".json", ".txt"))
        or re.search(r"_(cc|hh|hpp|h)$", value) is not None
    )


def _normalize_generated_path(module_name: str, path: Any) -> str:
    normalized = str(path)
    if normalized.startswith("08_geant4/"):
        normalized = normalized[len("08_geant4/") :]
    if module_name == "main_cmake" and normalized == "src/main.cc":
        return "main.cc"
    if module_name == "main_cmake" and normalized in {"run.mac", "init.mac"}:
        return f"macros/{normalized}"
    if "/" not in normalized and normalized not in {"CMakeLists.txt", "main.cc"}:
        if normalized.endswith(".cc"):
            return f"src/{normalized}"
        if normalized.endswith((".hh", ".hpp", ".h")):
            return f"include/{normalized}"
    snake_match = re.fullmatch(r"([a-z0-9_]+)_(cc|hh|hpp|h)", normalized)
    if snake_match:
        stem = "".join(part.capitalize() for part in snake_match.group(1).split("_"))
        ext = snake_match.group(2)
        directory = "src" if ext == "cc" else "include"
        return f"{directory}/{stem}.{ext}"
    return normalized


def save_module_result(
    result: ModuleAgentResult,
    job_id: str,
    raw_response: str | None = None,
) -> Path:
    """Persist module agent result to disk."""
    from agent_core.config.workspace import get_job_dir

    output_dir = get_job_dir(job_id) / "06_codegen" / "module_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{result.module_name}.json"
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    if raw_response is not None:
        raw_path = output_dir / f"{result.module_name}.raw.txt"
        raw_path.write_text(raw_response)
    return output_path
