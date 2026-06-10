"""Base class and utilities for module agents."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.paths import STAGE_CODEGEN

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
20. 顶层 module_name 必须等于当前 ModuleContext.module_name。
21. generated_files 中每个文件对象的 generated_by 必须等于
    "{当前模块名}_module_agent"，module_name 必须等于当前模块名；不得使用别名。
22. path 必须是相对 geant4_project 根目录的路径，例如 include/XXX.hh、src/XXX.cc、
    main.cc、CMakeLists.txt、macros/run.mac；不得以 geant4_project/ 开头。
23. 必须遵守 module_code_example 的 owned_files 和 primary_symbols；示例只用于接口形状，
    不能照抄成占位实现。
24. 生成代码前先检查 interface_context 和 existing_generated_file_summaries；
    调用上游模块时必须匹配其真实类名、构造函数和 public 方法。
25. 如果 Geant4 API、宏命令、ownership、构造函数或 scoring 访问方式不确定，
    必须优先使用 rag_snippets；RAG 不足时使用 web_context 中的可信 Geant4/CERN 来源。
26. 使用 RAG 或 web 得到的 API 事实必须写入 used_references；没有证据不得发明 API。
    used_references 必须是字符串数组，例如
    ["Geant4 Application Developers Guide: G4THitsCollection"]；
    不得返回对象、字典或嵌套数组。
27. 如果 ModuleContext.runtime_failure_context 非空，必须把其中 gate、build、ctest、
    smoke simulation、artifact contract 报告当作当前实现约束；只输出满足这些约束的新代码，
    不要复述旧失败过程。
28. 如果 ModuleContext 中包含 geant4_example_lookup_results，这是你在写代码前通过
    geant4_example_lookup 工具查看的 Geant4 B1/B2 示例片段。必须用这些片段核对真实接口，
    但不能照抄成与需求无关的示例程序。
29. 如果默认提供的 Geant4 示例片段仍不足以确认真实接口，可以先返回
    {"status":"needs_examples","geant4_example_requests":[...],"warnings":[],"errors":[]}
    请求 geant4_example_lookup。系统会执行工具并把片段放回 ModuleContext 后再次调用你。
    只有确实缺少接口证据时才请求工具；不要用工具请求代替代码生成。
30. 如果 existing_generated_file_summaries 或 context_coordination 仍不足以确认上游模块
    真实 C++ 接口，可以先返回
    {"status":"needs_code_context","code_context_requests":[...],"warnings":[],"errors":[]}
    请求 generated_code_lookup。系统会读取之前模块 agent 已生成的精确代码片段后再次调用你。
    优先请求 header 或最小 symbol 上下文，不要请求整个工程。

返回格式：
{
  "module_name": "...",
  "status": "generated",
  "generated_files": [
    {
      "path": "include/XXX.hh",
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

可选工具请求格式：
{
  "module_name": "...",
  "status": "needs_examples",
  "geant4_example_requests": [
    {
      "example": "B2b",
      "path": "src/DetectorConstruction.cc",
      "symbol": "ConstructSDandField",
      "query": "",
      "context_lines": 60,
      "max_chars": 6000
    }
  ],
  "warnings": [],
  "errors": []
}

或：
{
  "module_name": "...",
  "status": "needs_code_context",
  "code_context_requests": [
    {
      "path": "include/DetectorConstruction.hh",
      "symbol": "GetScoringVolume",
      "query": "",
      "context_lines": 60,
      "max_chars": 6000
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
    example_lookup_context = await _collect_example_lookup_context(
        gateway=gateway,
        module_name=module_name,
        module_context=module_context,
        job_id=job_id,
    )
    prompt_module_context = dict(module_context)
    if example_lookup_context:
        module_context["geant4_example_lookup_results"] = example_lookup_context
        prompt_module_context["geant4_example_lookup_results"] = example_lookup_context

    data: Any = {}
    file_entries: list[Any] = []
    for tool_round in range(3):
        user_prompt = _build_module_codegen_user_prompt(prompt_module_context, module_name)
        result = await gateway.call(
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            system_prompt=effective_system_prompt,
            user_prompt=user_prompt,
            response_format="json",
            max_tokens=65536,
            metadata={
                "module_name": module_name,
                "job_id": job_id,
                "enable_thinking": True,
                "tool_round": tool_round,
            },
        )

        if result.error:
            return ModuleAgentResult(
                module_name=module_name,
                status="failed",
                generated_files=[],
                errors=[f"Model call failed: {result.error}"],
            )

        try:
            data = result.parsed_json or json.loads(result.content.strip())
        except (json.JSONDecodeError, TypeError) as exc:
            repair = await _repair_module_json_response(
                gateway=gateway,
                module_name=module_name,
                job_id=job_id,
                raw_content=result.content or "",
                parse_error=exc,
                tool_round=tool_round,
            )
            if repair.error:
                return ModuleAgentResult(
                    module_name=module_name,
                    status="failed",
                    generated_files=[],
                    errors=[f"Invalid JSON response: {exc}; repair failed: {repair.error}"],
                )
            try:
                data = repair.parsed_json or json.loads(repair.content.strip())
            except (json.JSONDecodeError, TypeError) as repair_exc:
                return ModuleAgentResult(
                    module_name=module_name,
                    status="failed",
                    generated_files=[],
                    errors=[
                        "Invalid JSON response after repair: "
                        f"{repair_exc}; original parse error: {exc}"
                    ],
                )

        file_entries = _extract_generated_file_entries(data)
        example_requests = _extract_geant4_example_requests(data)
        code_context_requests = _extract_generated_code_context_requests(data)
        if (
            file_entries
            or (not example_requests and not code_context_requests)
            or module_name not in COARSE_CODEGEN_MODULES
        ):
            break
        if code_context_requests:
            lookup_result = _run_agent_requested_generated_code_lookup(
                code_context_requests,
                job_id=job_id,
                module_name=module_name,
                tool_round=tool_round + 1,
            )
            _append_generated_code_lookup_result(
                prompt_module_context,
                module_context,
                lookup_result,
                tool_round=tool_round + 1,
            )
        if example_requests:
            lookup_result = _run_agent_requested_example_lookup(
                example_requests,
                job_id=job_id,
                module_name=module_name,
                tool_round=tool_round + 1,
            )
            _append_example_lookup_result(
                prompt_module_context,
                module_context,
                lookup_result,
                tool_round=tool_round + 1,
            )

    # Build result
    generated_files: list[GeneratedModuleFile] = []
    parse_errors: list[str] = []
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
                    rationale=_normalize_string(f.get("rationale"), default=""),
                    dependencies=_normalize_string_list(f.get("dependencies", [])),
                    satisfies=_normalize_string_list(f.get("satisfies", [])),
                    risk_notes=_normalize_string_list(f.get("risk_notes", [])),
                    used_references=_normalize_string_list(f.get("used_references", [])),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
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
    _postprocess_generated_module_files(module_name, generated_files, module_context)

    return ModuleAgentResult(
        module_name=module_name,
        status=status,
        generated_files=generated_files,
        errors=errors,
        warnings=data.get("warnings", []),
    )


async def _repair_module_json_response(
    *,
    gateway: Any,
    module_name: str,
    job_id: str,
    raw_content: str,
    parse_error: Exception,
    tool_round: int,
) -> Any:
    repair_prompt = (
        "下面是上一轮模型输出，无法被 json.loads 解析。"
        "请只返回一个合法 JSON 对象，不要 Markdown fence，不要解释。"
        "JSON 顶层必须包含 module_name、status、generated_files、warnings、errors。"
        "generated_files 中每个文件对象必须使用 path 和 new_content。"
        f"\n\n解析错误: {parse_error}\n\n上一轮输出:\n{raw_content[-120000:]}"
    )
    return await gateway.call(
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt="You repair malformed model output into strict JSON only.",
        user_prompt=repair_prompt,
        response_format="json",
        max_tokens=65536,
        metadata={
            "module_name": module_name,
            "job_id": job_id,
            "enable_thinking": False,
            "tool_round": tool_round,
            "json_repair": True,
        },
    )


def _build_module_codegen_user_prompt(
    prompt_module_context: dict[str, Any],
    module_name: str,
) -> str:
    return f"""模块上下文：
{json.dumps(prompt_module_context, indent=2, ensure_ascii=False)}

请根据 ModuleContract 和 ModuleContext 生成当前模块的完整文件内容。
输出 JSON，不要输出额外文字。
JSON 顶层必须直接包含 module_name、status、generated_files、warnings、errors。
不得输出 {{"{module_name}": ...}} 这种按模块名包裹的嵌套对象。

如果 existing_generated_file_summaries/context_coordination 不足以确认上游模块真实 C++ 接口，
可以先返回 status="needs_code_context" 和 code_context_requests 数组请求工具。
工具请求必须少量、具体，优先读 include/*.hh 或某个 symbol 的上下文。

如果默认提供的 geant4_example_lookup_results 不足以确认 Geant4 真实接口，
可以先返回 status="needs_examples" 和 geant4_example_requests 数组请求工具。
工具请求必须少量、具体，并优先查 B2/B2a/B2b；runtime_app 可额外查 B1 启动方式。"""


def _extract_geant4_example_requests(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    status = str(data.get("status", "")).strip().lower()
    raw_requests = (
        data.get("geant4_example_requests")
        or data.get("example_lookup_requests")
        or data.get("tool_requests")
        or []
    )
    if status not in {"needs_examples", "need_examples", "tool_request"} and not raw_requests:
        return []
    if not isinstance(raw_requests, list):
        return []
    requests = [item for item in raw_requests if isinstance(item, dict)]
    return requests[:6]


def _extract_generated_code_context_requests(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    status = str(data.get("status", "")).strip().lower()
    raw_requests = (
        data.get("code_context_requests")
        or data.get("generated_code_requests")
        or data.get("generated_code_lookup_requests")
        or []
    )
    if (
        status not in {"needs_code_context", "need_code_context", "tool_request"}
        and not raw_requests
    ):
        return []
    if not isinstance(raw_requests, list):
        return []
    return [item for item in raw_requests if isinstance(item, dict)][:6]


def _run_agent_requested_generated_code_lookup(
    requests: list[dict[str, Any]],
    *,
    job_id: str,
    module_name: str,
    tool_round: int,
) -> dict[str, Any]:
    from agent_core.g4_codegen.context_coordinator import lookup_generated_code_snippets

    result = lookup_generated_code_snippets(
        requests,
        job_id=job_id,
        max_results=8,
    )
    result["requested_by_agent"] = True
    result["module_name"] = module_name
    result["tool_round"] = tool_round
    return result


def _append_generated_code_lookup_result(
    prompt_module_context: dict[str, Any],
    module_context: dict[str, Any],
    lookup_result: dict[str, Any],
    *,
    tool_round: int,
) -> None:
    for target in (prompt_module_context, module_context):
        existing = target.setdefault("generated_code_lookup_results", {})
        if not isinstance(existing, dict):
            existing = {"previous_value": existing}
            target["generated_code_lookup_results"] = existing
        rounds = existing.setdefault("agent_requested_lookup_rounds", [])
        if isinstance(rounds, list):
            rounds.append(
                {
                    "tool_round": tool_round,
                    "status": lookup_result.get("status"),
                    "requests": lookup_result.get("requests", []),
                    "snippets": lookup_result.get("snippets", []),
                    "errors": lookup_result.get("errors", []),
                }
            )


def _run_agent_requested_example_lookup(
    requests: list[dict[str, Any]],
    *,
    job_id: str,
    module_name: str,
    tool_round: int,
) -> dict[str, Any]:
    from agent_core.g4_codegen.example_lookup import lookup_geant4_example_snippets

    result = lookup_geant4_example_snippets(
        requests,
        job_id=job_id,
        module_name=f"{module_name}_agent_round_{tool_round}",
        max_results=6,
    )
    result["requested_by_agent"] = True
    result["tool_round"] = tool_round
    return result


def _append_example_lookup_result(
    prompt_module_context: dict[str, Any],
    module_context: dict[str, Any],
    lookup_result: dict[str, Any],
    *,
    tool_round: int,
) -> None:
    for target in (prompt_module_context, module_context):
        existing = target.setdefault("geant4_example_lookup_results", {})
        if not isinstance(existing, dict):
            existing = {"previous_value": existing}
            target["geant4_example_lookup_results"] = existing
        rounds = existing.setdefault("agent_requested_lookup_rounds", [])
        if isinstance(rounds, list):
            rounds.append(
                {
                    "tool_round": tool_round,
                    "status": lookup_result.get("status"),
                    "requests": lookup_result.get("requests", []),
                    "snippets": lookup_result.get("snippets", []),
                    "errors": lookup_result.get("errors", []),
                }
            )


COARSE_CODEGEN_MODULES = {"simulation_core", "beam_physics", "runtime_app"}

EXAMPLE_LOOKUP_SYSTEM_PROMPT = """你是 Geant4 示例检索规划 Agent。

你不写代码，只决定当前代码生成模块在动手前需要查看哪些本地 Geant4 示例片段。
可用工具是 geant4_example_lookup；工具可以按 example/path/symbol/query 返回 B1/B2 示例代码片段。

要求：
1. 优先请求 B2、B2a 或 B2b 示例；runtime_app 如需核对交互 UI 启动方式，也可请求 B1 main/CMake。
2. 每次只请求少量最相关文件或符号，不要请求整个示例目录。
3. 返回 JSON，不要输出额外文字。

返回格式：
{
  "tool_requests": [
    {
      "example": "B2b",
      "path": "src/DetectorConstruction.cc",
      "symbol": "ConstructSDandField",
      "query": "",
      "context_lines": 60,
      "max_chars": 6000
    }
  ],
  "rationale": "..."
}
"""


async def _collect_example_lookup_context(
    *,
    gateway: Any,
    module_name: str,
    module_context: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Let coarse codegen agents inspect local Geant4 examples before writing."""
    if module_name not in COARSE_CODEGEN_MODULES:
        return {}

    from agent_core.g4_codegen.example_lookup import (
        build_geant4_example_manifest,
        lookup_geant4_example_snippets,
    )

    manifest = build_geant4_example_manifest()
    if manifest.get("status") != "available":
        return {
            "tool_name": "geant4_example_lookup",
            "status": "unavailable",
            "errors": manifest.get("errors", []),
        }

    planning_context = {
        "module_name": module_name,
        "module_contract": module_context.get("module_contract", {}),
        "g4_model_ir_subset": _trim_for_example_planning(
            module_context.get("g4_model_ir_subset", {})
        ),
        "existing_generated_file_summaries": module_context.get(
            "existing_generated_file_summaries", []
        ),
        "example_manifest": _compact_example_manifest_for_prompt(manifest),
        "instruction": (
            "Return geant4_example_lookup requests for the minimal B2/B2a/B2b "
            "examples you need before writing this module. Do not write code."
        ),
    }

    tool_requests: list[dict[str, Any]] = _default_example_requests_for_module(module_name)
    planning_error = ""
    planner_enabled = os.getenv("RADAGENT_G4_EXAMPLE_LOOKUP_PLANNER", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if planner_enabled:
        try:
            plan_result = await gateway.call(
                task=ModelTask.CODEGEN,
                tier=ModelTier.PRO,
                system_prompt=EXAMPLE_LOOKUP_SYSTEM_PROMPT,
                user_prompt=json.dumps(planning_context, indent=2, ensure_ascii=False)[:24000],
                response_format="json",
                max_tokens=2048,
                metadata={
                    "module_name": module_name,
                    "job_id": job_id,
                    "codegen_stage": "example_lookup_planning",
                    "enable_thinking": True,
                },
            )
            if plan_result.error:
                planning_error = plan_result.error
            else:
                plan_data = plan_result.parsed_json or json.loads(plan_result.content.strip())
                planned_requests = _normalize_example_tool_requests(plan_data)
                if planned_requests:
                    tool_requests = planned_requests
        except Exception as exc:
            planning_error = str(exc)

    lookup_result = lookup_geant4_example_snippets(
        tool_requests,
        job_id=job_id,
        module_name=module_name,
        max_results=8,
    )
    return {
        "tool_name": "geant4_example_lookup",
        "status": lookup_result.get("status", "unavailable"),
        "planning_error": planning_error,
        "planner_enabled": planner_enabled,
        "planner_requested_examples": planner_enabled and not bool(planning_error),
        "requests": tool_requests,
        "snippets": lookup_result.get("snippets", []),
        "errors": lookup_result.get("errors", []),
        "usage_rule": (
            "Use these local Geant4 example snippets only to verify real Geant4 "
            "interfaces and launch patterns; adapt the generated project to the "
            "current G4ModelIR and module contract."
        ),
    }


def _normalize_example_tool_requests(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    raw_requests = data.get("tool_requests", data.get("requests", []))
    if not isinstance(raw_requests, list):
        return []
    requests: list[dict[str, Any]] = []
    for item in raw_requests:
        if isinstance(item, dict):
            requests.append(item)
    return requests[:8]


def _default_example_requests_for_module(module_name: str) -> list[dict[str, Any]]:
    if module_name == "simulation_core":
        return [
            {
                "example": "B2b",
                "path": "src/DetectorConstruction.cc",
                "symbol": "ConstructSDandField",
                "context_lines": 90,
                "max_chars": 9000,
            },
            {
                "example": "B2b",
                "path": "src/TrackerSD.cc",
                "symbol": "ProcessHits",
                "context_lines": 90,
                "max_chars": 9000,
            },
            {
                "example": "B2b",
                "path": "include/TrackerHit.hh",
                "symbol": "TrackerHit",
                "context_lines": 80,
                "max_chars": 7000,
            },
        ]
    if module_name == "beam_physics":
        return [
            {
                "example": "B2b",
                "path": "src/PrimaryGeneratorAction.cc",
                "symbol": "PrimaryGeneratorAction",
                "context_lines": 90,
                "max_chars": 9000,
            },
            {
                "example": "B2b",
                "path": "include/PrimaryGeneratorAction.hh",
                "symbol": "PrimaryGeneratorAction",
                "context_lines": 60,
                "max_chars": 5000,
            },
        ]
    if module_name == "runtime_app":
        return [
            {
                "example": "B2b",
                "path": "CMakeLists.txt",
                "query": "find_package",
                "context_lines": 90,
                "max_chars": 9000,
            },
            {
                "example": "B2b",
                "path": "exampleB2b.cc",
                "symbol": "G4UIExecutive",
                "context_lines": 110,
                "max_chars": 10000,
            },
            {
                "example": "B2b",
                "path": "src/ActionInitialization.cc",
                "symbol": "Build",
                "context_lines": 80,
                "max_chars": 7000,
            },
            {
                "example": "B1",
                "path": "exampleB1.cc",
                "symbol": "G4UIExecutive",
                "context_lines": 110,
                "max_chars": 10000,
            },
        ]
    return []


def _compact_example_manifest_for_prompt(manifest: dict[str, Any]) -> dict[str, Any]:
    examples = manifest.get("examples", {})
    compact_examples: dict[str, list[str]] = {}
    if isinstance(examples, dict):
        for example_name in ("B2b", "B2a", "B2", "B1"):
            files = examples.get(example_name, [])
            if not isinstance(files, list):
                continue
            preferred = [
                str(path)
                for path in files
                if str(path).endswith((".cc", ".hh", ".mac", "CMakeLists.txt"))
            ]
            compact_examples[example_name] = preferred[:80]
    return {
        "tool_name": manifest.get("tool_name", "geant4_example_lookup"),
        "status": manifest.get("status"),
        "examples": compact_examples,
        "request_schema": manifest.get("request_schema", {}),
    }


def _trim_for_example_planning(value: Any) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= 8000:
        return value
    return {"summary": text[:7960] + "\n[truncated for example planning]"}


def _normalize_module_status(value: Any) -> str:
    status = str(value or "generated").strip().lower()
    if status in {"generated", "success", "succeeded", "ok", "pass", "passed"}:
        return "generated"
    if status in {"repaired", "repair_success"}:
        return "repaired"
    return "failed"


def _normalize_string(value: Any, *, default: str) -> str:
    """Normalize model-returned scalar metadata into schema-compatible strings."""
    if value is None:
        return default
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_normalize_string(item, default="") for item in value]
        return "; ".join(part for part in parts if part) or default
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _postprocess_generated_module_files(
    module_name: str,
    generated_files: list[GeneratedModuleFile],
    module_context: dict[str, Any] | None = None,
) -> None:
    """Leave module-authored code untouched before final integration.

    The final integration agent now owns compile/runtime repair from real
    observations. Module postprocess rewrites previously introduced hidden,
    template-like fixes that could corrupt otherwise reviewable agent output.
    """
    return


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


def _normalize_string_list(value: Any) -> list[str]:
    """Normalize model-returned metadata fields that are schema-level string lists."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return [json.dumps(value, ensure_ascii=False, sort_keys=True)]

    normalized: list[str] = []
    for item in value:
        if item is None:
            continue
        if isinstance(item, str):
            normalized.append(item)
        elif isinstance(item, (int, float, bool)):
            normalized.append(str(item))
        else:
            normalized.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
    return normalized


def _looks_like_generated_file_path(value: str) -> bool:
    return (
        "/" in value
        or value in {"CMakeLists.txt", "main.cc"}
        or value.endswith((".cc", ".hh", ".hpp", ".h", ".mac", ".json", ".txt"))
        or re.search(r"_(cc|hh|hpp|h)$", value) is not None
    )


def _normalize_generated_path(module_name: str, path: Any) -> str:
    normalized = str(path)
    if normalized.startswith("geant4_project/"):
        normalized = normalized[len("geant4_project/") :]
    if module_name == "runtime_app" and normalized == "src/main.cc":
        return "main.cc"
    if module_name == "runtime_app" and normalized in {"run.mac", "init.mac"}:
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
    from agent_core.workspace.io import get_job_dir

    output_dir = get_job_dir(job_id) / STAGE_CODEGEN / "module_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{result.module_name}.json"
    output_path.write_text(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    if raw_response is not None:
        raw_path = output_dir / f"{result.module_name}.raw.txt"
        raw_path.write_text(raw_response)
    return output_path
