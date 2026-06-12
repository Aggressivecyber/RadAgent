"""Agentic module agents for Geant4 C++ codegen.

Each module agent runs a native tool-calling loop (read_file/write_file/edit_file)
against a SHARED staging workspace, so modules read each other's real headers and
align cross-module APIs exactly — instead of one-shot JSON generation that guessed
at sibling APIs from summaries.

The shared workspace lives under the codegen stage's ``module_workspace/`` dir and
accumulates files across file-groups, modules, and layers.
"""

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

FORBIDDEN_GENERATED_CONTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bTODO\b", re.IGNORECASE), "TODO marker"),
    (re.compile(r"\bNotImplemented\b", re.IGNORECASE), "NotImplemented marker"),
    (re.compile(r"\bstub\b", re.IGNORECASE), "stub marker"),
    (re.compile(r"\bdummy\b", re.IGNORECASE), "dummy marker"),
    (re.compile(r"\bplaceholder\b", re.IGNORECASE), "placeholder marker"),
]

MODULE_AGENTIC_SYSTEM_PROMPT = """\
你是 RadAgent 的 Geant4 C++ 模块级编码 Agent。你通过工具直接读写真实文件，
而不是返回 JSON。你只负责当前模块/文件组。

你可以读到的项目目录里可能已经有其他模块写好的头文件（include/*.hh）和
实现（src/*.cc）。**在调用其他模块的类、方法或类型前，必须先用 read_file
读取它的头文件，按真实签名对齐 API，不得凭摘要猜测。** 这是避免跨模块
API 不匹配的硬性要求。当前模块前一个文件组写出的接口若已出现在
`*_file_group.prior_files`，这是同一 agent 流程中的真实接口摘要，可直接使用，
不要再 read_file 同一模块刚生成的文件。

工具：
- read_file(path): 读取项目内文件（带行号）。写代码前先读依赖的头文件。
- write_file(path, content): 创建/完整覆盖一个你负责的文件。
- edit_file(path, old_string, new_string): 精确替换唯一匹配的片段（old_string
  必须在文件中唯一；不唯一就补上下文使之唯一）。

严格规则：
1. 只写当前模块/文件组拥有的文件（见 ModuleContext.module_contract.output_files）。
2. 不要 read_file 目录（例如 include、src 或 macros）；read_file 只用于具体文件。
3. 每个文件必须是完整内容，不得输出 Markdown fence、空 include、TODO/stub/dummy/placeholder。
4. 一个 assistant response 可以同时发出多个 write_file/edit_file tool calls。
   当 owned files 有多个时，优先在同一轮批量写出全部文件，不要一轮只写一个文件。
5. 任何使用 G4double/G4int/G4String/G4bool/CLHEP:: 的文件，必须在首次使用前
   #include 对应头（"globals.hh" 覆盖 G4double/G4int/G4String/G4bool；单位用
   "G4SystemOfUnits.hh"）。include 必须在匿名 namespace / constexpr 之前。
6. 不得实例化 Geant4 抽象基类；.hh 声明与 .cc 定义签名必须完全一致。
7. 调用上游模块的构造函数/公有方法前，read_file 其头文件，用真实类名、参数、
   方法名。ModuleContext.interface_context 只作职责参考，不作 API 事实来源。
8. 若 ModuleContext 含 geant4_example_lookup_results，用它核对真实 Geant4 接口，
   但不要照抄成与需求无关的示例。
9. 用单位时必须 include G4SystemOfUnits.hh；不得把 unsupported geometry 简化成 G4Box。

流程：
- 先 read_file 你依赖的其他模块上游头文件（若已存在于 include/）；同模块 prior_files 可直接用。
- 用 write_file 写出你拥有的每个文件（完整内容）；尽量在一次工具调用批次里写完所有 owned files。
- 写完所有 owned 文件后，停止调用工具，回复 DONE。
"""


async def run_module_agent(
    module_name: str,
    module_context: dict[str, Any],
    system_prompt: str = "",
) -> ModuleAgentResult:
    """Run an agentic module agent that writes real files into the shared workspace.

    Replaces the former one-shot JSON generation. The model receives read/write/edit
    tools scoped to the shared project dir, so it can read sibling modules' actual
    headers and align APIs. Owned files written by the model are collected into the
    result.
    """
    from agent_core.agent_loop import run_agent_loop
    from agent_core.dev_tools import DevToolkit
    from agent_core.workspace.io import get_job_dir

    job_id = (
        module_context.get("job_id")
        or module_context.get("g4_model_ir_subset", {}).get("job_id")
        or module_context.get("codegen_plan", {}).get("job_id")
        or ""
    )
    gateway = get_model_gateway()

    example_lookup_context = await _collect_example_lookup_context(
        gateway=gateway,
        module_name=module_name,
        module_context=module_context,
        job_id=job_id,
    )
    prompt_context = dict(module_context)
    if example_lookup_context:
        prompt_context["geant4_example_lookup_results"] = example_lookup_context

    contract = module_context.get("module_contract", {}) or {}
    output_files = [str(p) for p in (contract.get("output_files") or [])]

    # Shared staging workspace: later modules/layers read earlier modules' real
    # headers here. Lives under the codegen stage (the canonical geant4_project
    # is still written by the patch subgraph under STAGE_PATCH).
    project_dir = get_job_dir(job_id) / STAGE_CODEGEN / "module_workspace"
    project_dir.mkdir(parents=True, exist_ok=True)

    tool_policy = module_context.get("agent_tool_policy") or {}
    allow_read_file = bool(tool_policy.get("allow_read_file", True))
    tool_names = ["write_file", "edit_file"]
    if allow_read_file:
        tool_names.insert(0, "read_file")

    toolkit = DevToolkit(
        project_dir,
        job_id=job_id,
        tool_names=tool_names,
    )

    async def owned_files_written(_toolkit: DevToolkit, _audit: list[dict[str, Any]]) -> bool:
        return bool(output_files) and all((project_dir / rel).exists() for rel in output_files)

    def nudge_remaining_files(_audit: list[dict[str, Any]]) -> str | None:
        missing = [rel for rel in output_files if not (project_dir / rel).exists()]
        if not missing:
            return None
        return (
            "Remaining owned files still missing: "
            f"{', '.join(missing)}. Write these exact files next with complete content. "
            "Do not re-read files unless needed for a real dependency signature."
        )

    effective_system = (
        MODULE_AGENTIC_SYSTEM_PROMPT
        if not system_prompt
        else f"{MODULE_AGENTIC_SYSTEM_PROMPT}\n\n模块专用要求：\n{system_prompt}"
    )
    if not allow_read_file:
        effective_system = (
            f"{effective_system}\n\n"
            "本文件组的工具策略禁用了 read_file。必须依赖 ModuleContext、"
            "prior_files 和已给出的接口摘要直接写 owned files；不要请求读取文件。"
        )

    context_json = json.dumps(prompt_context, ensure_ascii=False, indent=2, default=str)
    if len(context_json) > 60_000:
        context_json = context_json[:60_000] + "\n...[module_context truncated]"
    owned = (
        ", ".join(output_files)
        if output_files
        else "the files owned by this module per module_contract"
    )
    dependency_instruction = (
        "- Before calling another module's class/method/type, read_file its header "
        "(under include/) to match the EXACT name and signature. Other modules may "
        "already have written headers there — read them; never guess APIs.\n"
        if allow_read_file
        else "- read_file is disabled for this file group; use ModuleContext and "
        "prior_files only, then write the owned files directly.\n"
    )
    user_message = (
        f"Module: {module_name}\n"
        f"Owned files to write now: {owned}\n\n"
        f"ModuleContext:\n{context_json}\n\n"
        "Instructions:\n"
        "- Use write_file to create each owned file with COMPLETE content.\n"
        "- In one assistant response, emit one write_file tool call per owned file "
        "whenever you already have enough interface information.\n"
        f"{dependency_instruction}"
        "- Apply the Geant4 rules in the system prompt (includes before use, etc.).\n"
        "- Write ONLY your owned files. When all are written, stop and reply DONE."
    )

    max_turns = max(
        4,
        _positive_int(os.getenv("RADAGENT_MODULE_AGENT_MAX_TURNS"), default=8),
    )
    loop_result = await run_agent_loop(
        gateway=gateway,
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt=effective_system,
        user_message=user_message,
        toolkit=toolkit,
        max_turns=max_turns,
        max_tokens=8192,
        stop_hook=owned_files_written,
        nudge_hook=nudge_remaining_files,
        metadata={
            "module_name": module_name,
            "job_id": job_id,
            "enable_thinking": False,
            "agentic_module": True,
        },
    )

    generated_files: list[GeneratedModuleFile] = []
    errors: list[str] = []
    for rel in output_files:
        target = project_dir / rel
        if target.exists():
            content = target.read_text(encoding="utf-8", errors="replace")
            generated_files.append(
                GeneratedModuleFile(
                    path=rel,
                    operation="create_or_replace",
                    new_content=content,
                    generated_by=f"{module_name}_module_agent",
                    module_name=module_name,
                    rationale=f"agentic generation ({loop_result.n_turns} turns, "
                    f"{len(loop_result.tool_audit)} tool calls)",
                )
            )
        else:
            errors.append(f"module agent did not write owned file: {rel}")

    warnings: list[str] = []
    if loop_result.stop_reason == "max_turns":
        warnings.append(f"agent loop reached max_turns={max_turns}")
    if loop_result.error:
        errors.append(f"agent loop error: {loop_result.error}")
    warnings.extend(_find_generated_content_issues(generated_files))

    status = "generated" if generated_files and not errors else "failed"
    return ModuleAgentResult(
        module_name=module_name,
        status=status,
        generated_files=generated_files,
        errors=errors,
        warnings=warnings,
        repair_attempts=[
            {
                "stop_reason": loop_result.stop_reason,
                "n_turns": loop_result.n_turns,
                "tool_calls": len(loop_result.tool_audit),
                "tool_audit": loop_result.tool_audit,
            }
        ],
    )


# ── Geant4 example pre-fetch (interface ground-truth before codegen) ─────────


COARSE_CODEGEN_MODULES = {"simulation_core", "beam_physics", "runtime_app"}

EXAMPLE_LOOKUP_SYSTEM_PROMPT = """\
你是 Geant4 示例检索规划 Agent。你不写代码，只决定当前模块动手前需要查看哪些
本地 Geant4 示例片段（B1/B2）。返回 JSON，不要输出额外文字。

返回格式：
{"tool_requests": [{"example":"B2b","path":"src/DetectorConstruction.cc","symbol":"ConstructSDandField","context_lines":60,"max_chars":6000}], "rationale":"..."}
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
        "1", "true", "yes", "on",
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
                    "enable_thinking": False,
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
        tool_requests, job_id=job_id, module_name=module_name, max_results=8,
    )
    return {
        "tool_name": "geant4_example_lookup",
        "status": lookup_result.get("status", "unavailable"),
        "planning_error": planning_error,
        "planner_enabled": planner_enabled,
        "requests": tool_requests,
        "snippets": lookup_result.get("snippets", []),
        "errors": lookup_result.get("errors", []),
        "usage_rule": (
            "Use these local Geant4 example snippets only to verify real Geant4 "
            "interfaces and launch patterns; adapt to the current G4ModelIR."
        ),
    }


def _normalize_example_tool_requests(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    raw_requests = data.get("tool_requests", data.get("requests", []))
    if not isinstance(raw_requests, list):
        return []
    return [item for item in raw_requests if isinstance(item, dict)][:8]


def _default_example_requests_for_module(module_name: str) -> list[dict[str, Any]]:
    if module_name == "simulation_core":
        return [
            {"example": "B2b", "path": "src/DetectorConstruction.cc", "symbol": "ConstructSDandField", "context_lines": 90, "max_chars": 9000},
            {"example": "B2b", "path": "src/TrackerSD.cc", "symbol": "ProcessHits", "context_lines": 90, "max_chars": 9000},
            {"example": "B2b", "path": "include/TrackerHit.hh", "symbol": "TrackerHit", "context_lines": 80, "max_chars": 7000},
        ]
    if module_name == "beam_physics":
        return [
            {"example": "B2b", "path": "src/PrimaryGeneratorAction.cc", "symbol": "PrimaryGeneratorAction", "context_lines": 90, "max_chars": 9000},
            {"example": "B2b", "path": "include/PrimaryGeneratorAction.hh", "symbol": "PrimaryGeneratorAction", "context_lines": 60, "max_chars": 5000},
        ]
    if module_name == "runtime_app":
        return [
            {"example": "B2b", "path": "CMakeLists.txt", "query": "find_package", "context_lines": 90, "max_chars": 9000},
            {"example": "B2b", "path": "exampleB2b.cc", "symbol": "G4UIExecutive", "context_lines": 110, "max_chars": 10000},
            {"example": "B2b", "path": "src/ActionInitialization.cc", "symbol": "Build", "context_lines": 80, "max_chars": 7000},
            {"example": "B1", "path": "exampleB1.cc", "symbol": "G4UIExecutive", "context_lines": 110, "max_chars": 10000},
        ]
    return []


def _compact_example_manifest_for_prompt(manifest: dict[str, Any]) -> dict[str, Any]:
    examples = manifest.get("examples", {})
    compact: dict[str, list[str]] = {}
    if isinstance(examples, dict):
        for name in ("B2b", "B2a", "B2", "B1"):
            files = examples.get(name, [])
            if isinstance(files, list):
                compact[name] = [
                    str(p) for p in files
                    if str(p).endswith((".cc", ".hh", ".mac", "CMakeLists.txt"))
                ][:80]
    return {
        "tool_name": manifest.get("tool_name", "geant4_example_lookup"),
        "status": manifest.get("status"),
        "examples": compact,
        "request_schema": manifest.get("request_schema", {}),
    }


def _trim_for_example_planning(value: Any) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= 8000:
        return value
    return {"summary": text[:7960] + "\n[truncated for example planning]"}


# ── Quality checks + persistence ─────────────────────────────────────────────


def _find_generated_content_issues(
    generated_files: list[GeneratedModuleFile],
) -> list[str]:
    issues: list[str] = []
    for file_entry in generated_files:
        for pattern, label in FORBIDDEN_GENERATED_CONTENT_PATTERNS:
            match = _first_matching_line(file_entry.new_content, pattern)
            if not match:
                continue
            line_no, snippet = match
            issues.append(
                f"{file_entry.path}: forbidden {label} at line {line_no}: {snippet}"
            )
            if len(issues) >= 12:
                return issues
    return issues


def _first_matching_line(
    content: str,
    pattern: re.Pattern[str],
) -> tuple[int, str] | None:
    for index, line in enumerate(content.splitlines(), start=1):
        if pattern.search(line):
            snippet = line.strip()
            if len(snippet) > 240:
                snippet = snippet[:237] + "..."
            return index, snippet
    return None


def _positive_int(value: Any, *, default: int) -> int:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if result > 0 else default


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
