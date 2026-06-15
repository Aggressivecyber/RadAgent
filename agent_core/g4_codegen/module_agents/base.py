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
import hashlib
from pathlib import Path
from typing import Any

from agent_core.g4_codegen.schemas import GeneratedModuleFile, ModuleAgentResult
from agent_core.g4_codegen.template_project import create_minimal_geant4_project
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
DEFAULT_MODULE_AGENT_HISTORY_CHARS = 48_000
DEFAULT_MODULE_CONTEXT_PROMPT_CHARS = 24_000
MODULE_CONTEXT_TRUNCATED_MARKER = "...[module_context truncated]"

MODULE_AGENTIC_SYSTEM_PROMPT = """\
你是 RadAgent 的 Geant4 C++ 模块级编码 Agent。你通过工具直接读写真实文件，
而不是返回 JSON。你只负责当前模块/文件组。

你可以读到的项目目录里可能已经有其他模块写好的头文件（include/*.hh）和
实现（src/*.cc）。**在调用其他模块的类、方法或类型前，必须先用 read_file
读取它的头文件，按真实签名对齐 API，不得凭摘要猜测。** 这是避免跨模块
API 不匹配的硬性要求。当前模块前一个文件组写出的接口若已出现在
`*_file_group.prior_files`，这是同一 agent 流程中的真实接口摘要，可直接使用，
不要再 read_file 同一模块刚生成的文件。

项目目录会预置 RadAgent canonical template：一套能 build/smoke run 的
Geant4 C++ 骨架，而不是关键词表单。你要读取并修改真实 C++ 接口
（DetectorConstruction、MaterialRegistry、PrimaryGeneratorAction、
OutputManager、ActionInitialization 等），不要把任务当成 fill keyword、
占位替换或配置表填空。

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
   常见 Geant4 类型也必须显式 include：G4ThreeVector 用 "G4ThreeVector.hh"；
   G4ParticleDefinition 用 "G4ParticleDefinition.hh"；G4Colour 用 "G4Colour.hh"；
   G4ParticleTable 用 "G4ParticleTable.hh"；G4Material 用 "G4Material.hh"；
   G4VSolid 用 "G4VSolid.hh"；G4ThreadLocal 用 "tls.hh"；
   不要写 G4THREADLOCAL；Hit::Draw 若使用 G4Circle 必须 include "G4Circle.hh"；
   std::vector/std::array/std::map 必须写对应标准库 include，例如
   #include <vector>。
   G4RotationMatrix 在 Geant4 11 中是 using/typedef 别名，不得写 class G4RotationMatrix;
   前向声明；任何声明/参数/字段使用 G4RotationMatrix 时必须 include "G4RotationMatrix.hh"。
   传给 G4PVPlacement 的 rotation pointer 类型必须是 G4RotationMatrix*，不要声明成
   const G4RotationMatrix*，否则会和 Geant4 构造函数签名不匹配。
6. 不得实例化 Geant4 抽象基类；.hh 声明与 .cc 定义签名必须完全一致。
7. 调用上游模块的构造函数/公有方法前，read_file 其头文件，用真实类名、参数、
   方法名。ModuleContext.interface_context 只作职责参考，不作 API 事实来源。
8. 若 ModuleContext 含 geant4_example_lookup_results，用它核对真实 Geant4 接口，
   但不要照抄成与需求无关的示例。
9. 用单位时必须 include G4SystemOfUnits.hh；不得把 unsupported geometry 简化成 G4Box。
10. 包裹/外壳/屏蔽体几何不得作为与被包裹体同级的实心重叠体放置。若一个体积包裹另一个体积，
    必须建成 shell/boolean subtraction，或把内部体积作为 daughter 放进容器；避免 GeomVol1002
    “same level fully encapsulating volume”。
11. voxel 网格必须根据物理尺寸设置有限 bin 数。不要用 10 um 这类过细默认值覆盖厘米级探测器；
    任何 vector/grid 分配前都要有 bin 上限，避免 std::length_error / max_size。
12. 若 ModuleContext.human_confirmation_context.confirmed_constraints 非空，这些是用户已确认硬约束；
    它们优先于默认推断、示例代码、RAG 摘要和你自己的猜测。生成几何、source、scoring、
    output artifact 时必须逐项落实 confirmed_constraints，不得静默改写或忽略。

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
    template_manifest = create_minimal_geant4_project(project_dir, events=100)
    preexisting_owned_hashes = _file_hashes(project_dir, output_files)

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
        return bool(output_files) and all(
            _owned_file_modified_by_current_agent(project_dir, rel, preexisting_owned_hashes, _audit)
            for rel in output_files
        )

    def nudge_remaining_files(_audit: list[dict[str, Any]]) -> str | None:
        missing = [
            rel
            for rel in output_files
            if not _owned_file_modified_by_current_agent(
                project_dir,
                rel,
                preexisting_owned_hashes,
                _audit,
            )
        ]
        if not missing:
            return None
        return (
            "Remaining owned files still not written or modified by this module agent: "
            f"{', '.join(missing)}. Use write_file or edit_file on these exact files next "
            "with complete task-specific content. Do not rely on the unchanged template file."
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

    context_prompt_chars = max(
        8_000,
        _positive_int(
            os.getenv("RADAGENT_MODULE_CONTEXT_PROMPT_CHARS"),
            default=DEFAULT_MODULE_CONTEXT_PROMPT_CHARS,
        ),
    )
    context_json = _module_context_json_for_prompt(
        prompt_context,
        max_chars=context_prompt_chars,
    )
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
        "Canonical template workspace:\n"
        "- The project directory already contains a buildable RadAgent Geant4 "
        "canonical template with stable interfaces and config/simulation_config.json.\n"
        "- Use read_file to inspect relevant template headers/sources before changing "
        "interfaces; use edit_file for focused changes when an owned file already exists.\n"
        "- This is not a keyword-fill task. Modify real C++ code and macros so the "
        "template implements the current G4ModelIR and human-confirmed constraints.\n"
        f"- Template manifest: {json.dumps(template_manifest, ensure_ascii=False)}\n\n"
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
    history_chars = max(
        8_000,
        _positive_int(
            os.getenv("RADAGENT_MODULE_AGENT_HISTORY_CHARS"),
            default=DEFAULT_MODULE_AGENT_HISTORY_CHARS,
        ),
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
        max_history_chars=history_chars,
        preserve_recent_tool_messages=1,
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
        if target.exists() and _owned_file_modified_by_current_agent(
            project_dir,
            rel,
            preexisting_owned_hashes,
            loop_result.tool_audit,
        ):
            original_content = target.read_text(encoding="utf-8", errors="replace")
            content = _postprocess_generated_module_content(rel, original_content)
            if content != original_content:
                target.write_text(content, encoding="utf-8")
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
            if target.exists():
                errors.append(f"module agent owned file not modified by current module agent: {rel}")
            else:
                errors.append(f"module agent did not write owned file: {rel}")

    warnings: list[str] = []
    if loop_result.stop_reason == "max_turns":
        warnings.append(f"agent loop reached max_turns={max_turns}")
    if loop_result.error:
        errors.append(f"agent loop error: {loop_result.error}")
    content_issues = _find_generated_content_issues(generated_files)
    warnings.extend(content_issues)
    errors.extend(_critical_generated_content_errors(content_issues))

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


def _module_context_json_for_prompt(
    prompt_context: dict[str, Any],
    *,
    max_chars: int,
) -> str:
    """Serialize module context with priority-preserving compaction."""
    full_json = json.dumps(prompt_context, ensure_ascii=False, indent=2, default=str)
    if len(full_json) <= max_chars:
        return full_json

    compact_context = _compact_module_context_for_prompt(prompt_context)
    compact_json = json.dumps(compact_context, ensure_ascii=False, indent=2, default=str)
    if len(compact_json) <= max_chars:
        return f"{compact_json}\n{MODULE_CONTEXT_TRUNCATED_MARKER}"

    keep_chars = max(0, max_chars - len(MODULE_CONTEXT_TRUNCATED_MARKER) - 1)
    return f"{compact_json[:keep_chars]}\n{MODULE_CONTEXT_TRUNCATED_MARKER}"


def _file_hashes(project_dir: Path, relative_paths: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in relative_paths:
        path = project_dir / relative
        if path.is_file():
            hashes[relative] = _file_sha256(path)
    return hashes


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _owned_file_modified_by_current_agent(
    project_dir: Path,
    relative_path: str,
    preexisting_hashes: dict[str, str],
    audit: list[dict[str, Any]],
) -> bool:
    path = project_dir / relative_path
    if not path.is_file():
        return False
    if relative_path not in preexisting_hashes:
        return True
    if _tool_audit_wrote_path(audit, relative_path):
        return True
    return _file_sha256(path) != preexisting_hashes[relative_path]


def _tool_audit_wrote_path(audit: list[dict[str, Any]], relative_path: str) -> bool:
    for entry in audit:
        if not entry.get("ok"):
            continue
        name = str(entry.get("name") or entry.get("tool") or "")
        if name not in {"write_file", "edit_file"}:
            continue
        arguments = entry.get("arguments")
        args = entry.get("args")
        parsed = args if isinstance(args, dict) else _json_dict(arguments)
        if str(parsed.get("path") or "") == relative_path:
            return True
        result = entry.get("result")
        if isinstance(result, dict) and str(result.get("path") or "") == relative_path:
            return True
    return False


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _compact_module_context_for_prompt(prompt_context: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}

    priority_keys = (
        "job_id",
        "module_name",
        "module_contract",
        "human_confirmation_context",
        "runtime_failure_context",
        "agentic_repair_lessons",
        "confirmed_model_plan_path",
        "confirmation_record_path",
        "human_confirmation_status",
        "agent_tool_policy",
        "interface_context",
    )
    for key in priority_keys:
        if key in prompt_context:
            compact[key] = _trim_prompt_value(prompt_context[key], max_chars=8_000)

    for key, value in prompt_context.items():
        if key.endswith("_file_group"):
            compact[key] = _compact_file_group_for_prompt(value)

    if "g4_model_ir_subset" in prompt_context:
        compact["g4_model_ir_subset"] = _trim_prompt_value(
            prompt_context["g4_model_ir_subset"],
            max_chars=6_000,
        )
    if "existing_generated_file_summaries" in prompt_context:
        compact["existing_generated_file_summaries"] = _compact_file_summaries_for_prompt(
            prompt_context["existing_generated_file_summaries"]
        )
    if "geant4_example_lookup_results" in prompt_context:
        compact["geant4_example_lookup_results"] = _compact_example_lookup_for_prompt(
            prompt_context["geant4_example_lookup_results"]
        )

    secondary_keys = (
        "context_retrieval_policy",
        "run_mode",
        "module_code_example",
        "rag_snippets",
        "web_context",
        "retrieved_context",
        "codegen_plan",
    )
    for key in secondary_keys:
        if key in prompt_context and key not in compact:
            compact[key] = _trim_prompt_value(prompt_context[key], max_chars=4_000)

    for key, value in prompt_context.items():
        if key in compact or key.endswith("_file_group"):
            continue
        compact[key] = _trim_prompt_value(value, max_chars=2_000)

    return compact


def _compact_file_group_for_prompt(value: Any) -> Any:
    if not isinstance(value, dict):
        return _trim_prompt_value(value, max_chars=4_000)
    compact = dict(value)
    compact["prior_files"] = _compact_file_summaries_for_prompt(value.get("prior_files", []))
    return _trim_prompt_value(compact, max_chars=8_000)


def _compact_file_summaries_for_prompt(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    summaries: list[Any] = []
    for item in value[:32]:
        if not isinstance(item, dict):
            summaries.append(_trim_prompt_value(item, max_chars=800))
            continue
        kept: dict[str, Any] = {}
        for key in (
            "path",
            "module_name",
            "generated_by",
            "classes",
            "constructor_signatures",
            "public_methods",
            "public_method_signatures",
            "methods",
            "fields",
            "includes",
            "provided_symbols",
            "consumed_symbols",
            "output_contract",
        ):
            if key in item:
                kept[key] = _trim_prompt_value(item[key], max_chars=2_000)
        if "header_or_interface_content" in item:
            kept["header_or_interface_content"] = _trim_text_for_prompt(
                item["header_or_interface_content"],
                max_chars=1_200,
            )
        if not kept:
            kept = _trim_prompt_value(item, max_chars=1_200)
        summaries.append(kept)
    if len(value) > 32:
        summaries.append({"omitted_file_summaries": len(value) - 32})
    return summaries


def _compact_example_lookup_for_prompt(value: Any) -> Any:
    if not isinstance(value, dict):
        return _trim_prompt_value(value, max_chars=6_000)
    compact: dict[str, Any] = {}
    for key in (
        "tool_name",
        "status",
        "planning_error",
        "planner_enabled",
        "requests",
        "errors",
        "usage_rule",
    ):
        if key in value:
            compact[key] = _trim_prompt_value(value[key], max_chars=2_000)
    snippets = value.get("snippets", [])
    if isinstance(snippets, list):
        compact["snippets"] = [
            _trim_prompt_value(snippet, max_chars=1_800)
            for snippet in snippets[:6]
        ]
        if len(snippets) > 6:
            compact["omitted_snippets"] = len(snippets) - 6
    return compact


def _trim_prompt_value(value: Any, *, max_chars: int) -> Any:
    if isinstance(value, str):
        return _trim_text_for_prompt(value, max_chars=max_chars)
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= max_chars:
        return value
    return {
        "summary": _trim_text_for_prompt(text, max_chars=max_chars),
        "original_chars": len(text),
    }


def _trim_text_for_prompt(value: Any, *, max_chars: int) -> str:
    text = str(value)
    if len(text) <= max_chars:
        return text
    keep_chars = max(0, max_chars - 48)
    return f"{text[:keep_chars]}\n...[truncated {len(text) - keep_chars} chars]"


def _postprocess_generated_module_content(path: str, content: str) -> str:
    if path == "src/SensitiveDetector.cc":
        content = _qualify_sensitive_detector_hit_type(content)
        content = _replace_sensitive_detector_placeholder_event_id(content)
        content = _remove_sensitive_detector_stale_placeholder_comments(content)
    if path == "src/OutputManager.cc":
        content = _ensure_summary_events_requested(content)
        content = _remove_noop_output_manager_summary_overload(content)
        content = _normalize_output_manager_filesystem_paths(content)
        content = _ensure_output_manager_deposit_fallbacks(content)
    if path == "src/DetectorConstruction.cc":
        content = _normalize_detector_scoring_manager_api(content)
        content = _remove_detector_legacy_physical_volume_registry_calls(content)
    if path == "include/ScoringManager.hh":
        content = _ensure_scoring_manager_stable_header_api(content)
    if path == "src/ScoringManager.cc":
        content = _ensure_scoring_manager_stable_source_api(content)
    if path == "main.cc":
        content = _replace_shell_mkdir_with_filesystem(content)
    if path.endswith((".cc", ".cpp", ".cxx", ".hh", ".hpp", ".h")):
        content = _normalize_threadlocal_macro(content)
        content = _normalize_rotation_matrix_pointer_constness(content)
        content = _normalize_vis_attributes_member_access(content)
    if path.endswith((".cc", ".cpp", ".cxx", ".hh", ".hpp", ".h")):
        content = _ensure_required_geant4_includes(content)
    if path.endswith(".mac"):
        content = _normalize_macro_cut_commands(content)
    return content


def _qualify_sensitive_detector_hit_type(content: str) -> str:
    """Avoid G4VSensitiveDetector::Hit hiding the project Hit class."""
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
    content = re.sub(
        r"(?<![:\w])Hit\s*\*\s*([A-Za-z_]\w*)\s*=\s*dynamic_cast\s*<\s*Hit\s*\*\s*>\s*\(",
        r"::Hit* \1 = dynamic_cast<::Hit*>(",
        content,
    )
    content = re.sub(
        r"(?<![:\w])Hit\s*\*\s*([A-Za-z_]\w*)\s*=\s*(\(\s*\*\s*fHitsCollection\s*\)\s*\[[^\]]+\]\s*;)",
        r"::Hit* \1 = \2",
        content,
    )
    return content


def _replace_sensitive_detector_placeholder_event_id(content: str) -> str:
    if not re.search(r"\bSetEventID\s*\(\s*0\s*\)", content):
        return content

    replacement = (
        "const G4Event* currentEvent = "
        "G4RunManager::GetRunManager()->GetCurrentEvent();\n"
        "  hit->SetEventID(currentEvent ? currentEvent->GetEventID() : -1);"
    )
    return re.sub(
        r"(?P<indent>[ \t]*)hit->SetEventID\s*\(\s*0\s*\)\s*;"
        r"(?:[ \t]*(?://[^\n]*placeholder[^\n]*)?)",
        lambda match: (
            f"{match.group('indent')}{replacement.replace(chr(10), chr(10) + match.group('indent'))}"
        ),
        content,
        count=1,
        flags=re.IGNORECASE,
    )


def _remove_sensitive_detector_stale_placeholder_comments(content: str) -> str:
    lines: list[str] = []
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        lowered = stripped.lower()
        is_comment = stripped.startswith("//")
        stale_event_track_comment = (
            is_comment
            and "placeholder" in lowered
            and ("event" in lowered or "track" in lowered)
            and "not a placeholder" not in lowered
            and "no placeholder" not in lowered
            and "without placeholder" not in lowered
        )
        if stale_event_track_comment:
            continue
        lines.append(line)
    return "".join(lines)


def _normalize_detector_scoring_manager_api(content: str) -> str:
    content = content.replace(
        "fScoringManager = new ScoringManager();",
        "fScoringManager = ScoringManager::Instance();",
    )
    content = re.sub(
        r"(?P<indent>[ \t]*)delete\s+fScoringManager\s*;[ \t]*(?://[^\n]*)?",
        r"\g<indent>// fScoringManager is a singleton; do not delete it.",
        content,
    )
    return re.sub(
        r"(?P<indent>[ \t]*)fScoringManager->RegisterRegionScoring\s*\(\s*"
        r"(?P<component>[^,\n;]+)\s*,\s*(?P<volume>[^)\n;]+)\s*\)\s*;",
        _detector_register_region_replacement,
        content,
    )


def _detector_register_region_replacement(match: re.Match[str]) -> str:
    indent = match.group("indent")
    component = match.group("component").strip()
    volume = match.group("volume").strip()
    return (
        f"{indent}G4double regionMassKg = {volume}->GetMass(true, false) / kg;\n"
        f"{indent}fScoringManager->RegisterRegion({component}, regionMassKg);"
    )


def _remove_detector_legacy_physical_volume_registry_calls(content: str) -> str:
    return re.sub(
        r"(?P<indent>[ \t]*)(?P<object>[A-Za-z_]\w*)->PlaceVolume\s*\(\s*"
        r'"(?P<component>[^"]+)"\s*,\s*(?P<physical>[A-Za-z_]\w*)\s*\)\s*;',
        (
            r"\g<indent>// legacy physical-volume registry call removed; "
            r"PlacementManager::PlaceVolume creates placements from logical volumes."
        ),
        content,
    )


def _ensure_scoring_manager_stable_header_api(content: str) -> str:
    if "class ScoringManager" not in content or "public:" not in content:
        return content

    additions: list[str] = []
    if not re.search(
        r"\bstatic\s+ScoringManager\s*\*\s*Instance\s*\(\s*\)\s*;",
        content,
    ):
        additions.append("  static ScoringManager* Instance();")
    has_two_arg_register = re.search(
        r"\bvoid\s+RegisterRegion\s*\(\s*const\s+G4String\s*&\s*\w+\s*,\s*"
        r"G4double\s+\w+\s*\)\s*;",
        content,
        flags=re.DOTALL,
    )
    has_quantity_register = re.search(
        r"\bvoid\s+RegisterRegion\s*\([^;]*std::vector\s*<\s*G4String\s*>[^;]*\)\s*;",
        content,
        flags=re.DOTALL,
    )
    if has_quantity_register and not has_two_arg_register:
        additions.append("  void RegisterRegion(const G4String& componentId, G4double massKg);")
    if not additions:
        return content

    def insert_after_public(match: re.Match[str]) -> str:
        return match.group(0) + "\n".join(additions) + "\n"

    return re.sub(r"(?m)^[ \t]*public:\s*\n", insert_after_public, content, count=1)


def _ensure_scoring_manager_stable_source_api(content: str) -> str:
    if "ScoringManager::" not in content:
        return content

    if not re.search(r"\bScoringManager\s*\*\s*ScoringManager::Instance\s*\(", content):
        instance_impl = (
            "ScoringManager* ScoringManager::Instance()\n"
            "{\n"
            "  static ScoringManager instance;\n"
            "  return &instance;\n"
            "}\n\n"
        )
        content = _insert_after_include_block(content, instance_impl)

    has_two_arg_register = re.search(
        r"\bvoid\s+ScoringManager::RegisterRegion\s*\(\s*"
        r"const\s+G4String\s*&\s*\w+\s*,\s*G4double\s+\w+\s*\)",
        content,
        flags=re.DOTALL,
    )
    has_quantity_register = re.search(
        r"\bvoid\s+ScoringManager::RegisterRegion\s*\([^)]*std::vector\s*<\s*"
        r"G4String\s*>[^)]*\)",
        content,
        flags=re.DOTALL,
    )
    if has_quantity_register and not has_two_arg_register:
        overload_impl = (
            "\nvoid ScoringManager::RegisterRegion(const G4String& componentId, G4double massKg)\n"
            "{\n"
            '  RegisterRegion(componentId, massKg, {"edep_MeV", "dose_Gy"});\n'
            "}\n"
        )
        content = content.rstrip() + "\n" + overload_impl

    return content


def _ensure_summary_events_requested(content: str) -> str:
    if '\\"events_requested\\"' in content:
        return content
    replacements = (
        (
            '  ofs << "  \\"total_events\\": " << totalEvents << ",\\n";',
            '  ofs << "  \\"events_requested\\": " << totalEvents << ",\\n";',
        ),
        (
            '  ofs << "  \\"total_events\\": " << totalEvents << "," << std::endl;',
            '  ofs << "  \\"events_requested\\": " << totalEvents << "," << std::endl;',
        ),
    )
    for total_events_line, events_requested_line in replacements:
        if total_events_line not in content:
            continue
        return content.replace(
            total_events_line,
            total_events_line + "\n" + events_requested_line,
            1,
        )
    return content


def _remove_noop_output_manager_summary_overload(content: str) -> str:
    if "OutputManager::WriteSummaryJson()" not in content:
        return content
    if not re.search(r"OutputManager::WriteSummaryJson\s*\(\s*G4int\b", content):
        return content
    return re.sub(
        r"\n?void\s+OutputManager::WriteSummaryJson\s*\(\s*\)\s*"
        r"\{\s*(?:(?://[^\n]*\n)|(?:/\*.*?\*/)|\s)*\}\s*\n?",
        "\n",
        content,
        count=1,
        flags=re.DOTALL,
    )


def _normalize_output_manager_filesystem_paths(content: str) -> str:
    if "std::filesystem::path" not in content or "fOutputDir" not in content:
        return content
    content = re.sub(
        r"std::filesystem::path\s+([A-Za-z_]\w*)\s*\(\s*fOutputDir\s*\)",
        r"std::filesystem::path \1(fOutputDir.c_str())",
        content,
    )
    content = re.sub(
        r"=\s*fOutputDir\s*/",
        r"= std::filesystem::path(fOutputDir.c_str()) /",
        content,
    )
    return content


def _ensure_output_manager_deposit_fallbacks(content: str) -> str:
    if "_BuildEventRowsFromDeposits" in content:
        return content
    content = _ensure_output_manager_energy_deposit_event_fallback(content)
    content = _ensure_output_manager_energy_deposit_points_fallback(content)
    required_tokens = ("fDeposits", "fEventRows", "fVoxelBins")
    if not all(token in content for token in required_tokens):
        return content

    helper = """namespace {
constexpr G4double kRadAgentFallbackDosePerMeV = 1.602176634e-13;

bool _HasPositiveEventRows(const std::vector<EventRow>& rows)
{
    for (const auto& row : rows) {
        if (row.edepMeV > 0.0 || row.doseGy > 0.0) {
            return true;
        }
    }
    return false;
}

std::vector<EventRow> _BuildEventRowsFromDeposits(
    const std::vector<EventRow>& rows,
    const std::vector<EnergyDepositRecord>& deposits,
    G4int eventsRequested)
{
    if (_HasPositiveEventRows(rows) || deposits.empty()) {
        return rows;
    }

    G4int rowCount = eventsRequested > 0 ? eventsRequested : 0;
    for (const auto& deposit : deposits) {
        if (deposit.eventID >= rowCount) {
            rowCount = deposit.eventID + 1;
        }
    }

    std::vector<EventRow> derived;
    derived.reserve(static_cast<std::size_t>(rowCount));
    for (G4int eventID = 0; eventID < rowCount; ++eventID) {
        derived.push_back({eventID, 0.0, 0.0});
    }

    for (const auto& deposit : deposits) {
        if (deposit.eventID < 0 || deposit.eventID >= rowCount || deposit.edepMeV <= 0.0) {
            continue;
        }
        auto& row = derived[static_cast<std::size_t>(deposit.eventID)];
        row.edepMeV += deposit.edepMeV;
        row.doseGy += deposit.edepMeV * kRadAgentFallbackDosePerMeV;
    }
    return derived;
}

bool _HasPositiveVoxelBins(const std::vector<VoxelBin>& bins)
{
    for (const auto& bin : bins) {
        if (bin.edepMeV > 0.0 || bin.doseGy > 0.0) {
            return true;
        }
    }
    return false;
}

std::vector<VoxelBin> _BuildVoxelBinsFromDeposits(
    const std::vector<VoxelBin>& bins,
    const std::vector<EnergyDepositRecord>& deposits)
{
    if (_HasPositiveVoxelBins(bins) || deposits.empty()) {
        return bins;
    }

    std::vector<VoxelBin> derived;
    derived.reserve(deposits.size());
    for (const auto& deposit : deposits) {
        if (deposit.edepMeV <= 0.0) {
            continue;
        }
        derived.push_back({
            deposit.x,
            deposit.y,
            deposit.z,
            deposit.edepMeV,
            deposit.edepMeV * kRadAgentFallbackDosePerMeV,
        });
    }
    return derived;
}
}

"""
    content = _insert_after_include_block(content, helper)
    content = re.sub(
        r"(?P<indent>[ \t]*)for\s*\(\s*const\s+auto&\s+r\s*:\s*fEventRows\s*\)\s*"
        r"totalEdep\s*\+=\s*r\.edepMeV\s*;",
        (
            r"\g<indent>const auto eventRowsForOutput = "
            r"_BuildEventRowsFromDeposits(fEventRows, fDeposits, fEventsRequested);\n"
            r"\g<indent>for (const auto& r : eventRowsForOutput) totalEdep += r.edepMeV;"
        ),
        content,
        count=1,
    )
    content = content.replace("fEventRows.size()", "eventRowsForOutput.size()", 1)
    content = re.sub(
        r"(?P<indent>[ \t]*)for\s*\(\s*const\s+auto&\s+r\s*:\s*fEventRows\s*\)\s*\{",
        (
            r"\g<indent>const auto eventRowsForOutput = "
            r"_BuildEventRowsFromDeposits(fEventRows, fDeposits, fEventsRequested);\n"
            r"\g<indent>for (const auto& r : eventRowsForOutput) {"
        ),
        content,
        count=1,
    )
    content = re.sub(
        r"(?P<indent>[ \t]*)for\s*\(\s*const\s+auto&\s+b\s*:\s*fVoxelBins\s*\)\s*\{",
        (
            r"\g<indent>const auto voxelBinsForOutput = "
            r"_BuildVoxelBinsFromDeposits(fVoxelBins, fDeposits);\n"
            r"\g<indent>for (const auto& b : voxelBinsForOutput) {"
        ),
        content,
    )
    return content


def _ensure_output_manager_energy_deposit_points_fallback(content: str) -> str:
    required_tokens = ("fEnergyDepositPoints", "fEventRows")
    if not all(token in content for token in required_tokens):
        return content
    event_edep_field, event_dose_field = _event_row_energy_and_dose_fields(content)
    if not event_edep_field or not event_dose_field:
        event_edep_field, event_dose_field = "edep_MeV", "dose_Gy"
    point_edep_field = _energy_deposit_point_edep_field(content) or event_edep_field
    helper = """namespace {
constexpr G4double kRadAgentPointFallbackDosePerMeV = 1.602176634e-13;

bool _HasPositiveEventRowsFromPoints(const std::vector<EventRow>& rows)
{
    for (const auto& row : rows) {
        if (row.EVENT_EDEP_FIELD > 0.0 || row.EVENT_DOSE_FIELD > 0.0) {
            return true;
        }
    }
    return false;
}

bool _RadAgentRowsNeedDoseBackfill(const std::vector<EventRow>& rows)
{
    for (const auto& row : rows) {
        if (row.EVENT_EDEP_FIELD > 0.0 && row.EVENT_DOSE_FIELD <= 0.0) {
            return true;
        }
    }
    return false;
}

std::vector<EventRow> _BuildEventRowsFromEnergyDepositPoints(
    const std::vector<EventRow>& rows,
    const std::vector<EnergyDepositPoint>& points,
    G4int eventsRequested)
{
    if (_RadAgentRowsNeedDoseBackfill(rows)) {
        std::vector<EventRow> backfilledRows = rows;
        for (auto& backfilled : backfilledRows) {
            if (backfilled.EVENT_EDEP_FIELD > 0.0 && backfilled.EVENT_DOSE_FIELD <= 0.0) {
                backfilled.EVENT_DOSE_FIELD = backfilled.EVENT_EDEP_FIELD * kRadAgentPointFallbackDosePerMeV;
            }
        }
        return backfilledRows;
    }
    if (_HasPositiveEventRowsFromPoints(rows) || points.empty()) {
        return rows;
    }
    G4int rowCount = eventsRequested > 0 ? eventsRequested : 0;
    for (const auto& point : points) {
        if (point.eventID >= rowCount) {
            rowCount = point.eventID + 1;
        }
    }
    std::vector<EventRow> eventRowsFromEnergyDepositPoints;
    eventRowsFromEnergyDepositPoints.reserve(static_cast<std::size_t>(rowCount));
    for (G4int eventID = 0; eventID < rowCount; ++eventID) {
        eventRowsFromEnergyDepositPoints.push_back({eventID, 0.0, 0.0});
    }
    for (const auto& point : points) {
        if (point.eventID < 0 || point.eventID >= rowCount || point.POINT_EDEP_FIELD <= 0.0) {
            continue;
        }
        auto& row = eventRowsFromEnergyDepositPoints[static_cast<std::size_t>(point.eventID)];
        row.EVENT_EDEP_FIELD += point.POINT_EDEP_FIELD;
        row.EVENT_DOSE_FIELD += point.POINT_EDEP_FIELD * kRadAgentPointFallbackDosePerMeV;
    }
    return eventRowsFromEnergyDepositPoints;
}
}

"""
    helper = helper.replace("EVENT_EDEP_FIELD", event_edep_field)
    helper = helper.replace("EVENT_DOSE_FIELD", event_dose_field)
    helper = helper.replace("POINT_EDEP_FIELD", point_edep_field)
    if "eventRowsFromEnergyDepositPoints" not in content:
        content = _insert_after_include_block(content, helper)
        content = re.sub(
            r"(?P<indent>[ \t]*)G4int\s+totalEvents\s*=\s*static_cast<G4int>\s*\(\s*fEventRows\.size\(\)\s*\)\s*;",
            (
                r"\g<indent>const auto eventRowsForOutput = "
                r"_BuildEventRowsFromEnergyDepositPoints(fEventRows, fEnergyDepositPoints, fEventsRequested);\n"
                r"\g<indent>G4int totalEvents = static_cast<G4int>(eventRowsForOutput.size());"
            ),
            content,
            count=1,
        )
    content = _ensure_output_manager_point_dose_backfill(content)
    content = _ensure_output_manager_point_event_table_rows(content)
    content = _ensure_output_manager_point_summary_event_rows(content)
    return content


def _ensure_output_manager_point_event_table_rows(content: str) -> str:
    return _ensure_event_rows_for_output_in_function(
        content,
        "void OutputManager::WriteEventTableCsv",
    )


def _ensure_output_manager_point_summary_event_rows(content: str) -> str:
    return _ensure_event_rows_for_output_in_function(
        content,
        "void OutputManager::WriteSummaryJson",
    )


def _ensure_output_manager_point_dose_backfill(content: str) -> str:
    if "_BuildEventRowsFromEnergyDepositPoints" not in content:
        return content
    if "_RadAgentRowsNeedDoseBackfill" in content and "backfilledRows" in content:
        return content

    edep_field, dose_field = _event_row_energy_and_dose_fields(content)
    if not edep_field or not dose_field:
        return content
    dose_expr = _event_row_dose_backfill_expression(content)
    checker = f"""
bool _RadAgentRowsNeedDoseBackfill(const std::vector<EventRow>& rows)
{{
    for (const auto& row : rows) {{
        if (row.{edep_field} > 0.0 && row.{dose_field} <= 0.0) {{
            return true;
        }}
    }}
    return false;
}}
"""
    function_start = content.find("std::vector<EventRow> _BuildEventRowsFromEnergyDepositPoints")
    if function_start < 0:
        return content
    content = content[:function_start] + checker + content[function_start:]
    function_start = content.find("std::vector<EventRow> _BuildEventRowsFromEnergyDepositPoints")
    open_brace = content.find("{", function_start)
    if open_brace < 0:
        return content
    injection = f"""
    if (_RadAgentRowsNeedDoseBackfill(rows)) {{
        std::vector<EventRow> backfilledRows = rows;
        for (auto& backfilled : backfilledRows) {{
            if (backfilled.{edep_field} > 0.0 && backfilled.{dose_field} <= 0.0) {{
                backfilled.{dose_field} = backfilled.{edep_field} * {dose_expr};
            }}
        }}
        return backfilledRows;
    }}
"""
    return content[: open_brace + 1] + injection + content[open_brace + 1 :]


def _event_row_energy_and_dose_fields(content: str) -> tuple[str, str]:
    if re.search(r"\.\s*edep_MeV\b", content) and re.search(r"\.\s*dose_Gy\b", content):
        return "edep_MeV", "dose_Gy"
    if re.search(r"\.\s*edepMeV\b", content) and re.search(r"\.\s*doseGy\b", content):
        return "edepMeV", "doseGy"
    if re.search(r"\bEventRow\b[^;{]*\{[^}]*\bedepMeV\b[^}]*\bdoseGy\b", content):
        return "edepMeV", "doseGy"
    if re.search(r"\bEventRow\b[^;{]*\{[^}]*\bedep_MeV\b[^}]*\bdose_Gy\b", content):
        return "edep_MeV", "dose_Gy"
    return "", ""


def _energy_deposit_point_edep_field(content: str) -> str:
    if re.search(r"\.\s*edep_MeV\b", content):
        return "edep_MeV"
    if re.search(r"\.\s*edepMeV\b", content):
        return "edepMeV"
    if re.search(r"\bEnergyDepositPoint\b[^;{]*\{[^}]*\bedepMeV\b", content):
        return "edepMeV"
    if re.search(r"\bEnergyDepositPoint\b[^;{]*\{[^}]*\bedep_MeV\b", content):
        return "edep_MeV"
    return ""


def _event_row_dose_backfill_expression(content: str) -> str:
    if "kMeVtoJ" in content and "kSiliconDetectorMassKg" in content:
        return "kMeVtoJ / kSiliconDetectorMassKg"
    if "kRadAgentPointFallbackDosePerMeV" in content:
        return "kRadAgentPointFallbackDosePerMeV"
    return "1.602176634e-13"


def _ensure_event_rows_for_output_in_function(content: str, marker: str) -> str:
    start = content.find(marker)
    if start < 0:
        return content

    prefix = content[:start]
    suffix = content[start:]
    if "fEventRows" not in suffix:
        return content

    open_brace = suffix.find("{")
    if open_brace < 0:
        return content
    close_brace = _find_matching_brace_in_text(suffix, open_brace)
    if close_brace < 0:
        return content
    func_body = suffix[: close_brace + 1]
    rest = suffix[close_brace + 1 :]

    loop_pattern = (
        r"(?P<indent>[ \t]*)for\s*\(\s*const\s+auto&\s+(?P<var>[A-Za-z_]\w*)\s*:\s*fEventRows\s*\)\s*\{"
    )
    if not re.search(loop_pattern, func_body) and "fEventRows.size()" not in func_body:
        return content

    builder_call = (
        "_BuildEventRowsFromEnergyDepositPoints("
        "fEventRows, fEnergyDepositPoints, fEventsRequested)"
    )
    if builder_call not in func_body:
        indent_match = re.search(r"\n(?P<indent>[ \t]*)\S", func_body[open_brace + 1 :])
        indent = indent_match.group("indent") if indent_match else "    "
        declaration = f"\n{indent}const auto eventRowsForOutput = {builder_call};"
        func_body = func_body[: open_brace + 1] + declaration + func_body[open_brace + 1 :]

    func_body = func_body.replace("fEventRows.size()", "eventRowsForOutput.size()", 1)
    func_body = re.sub(
        loop_pattern,
        lambda match: (
            f"{match.group('indent')}for (const auto& {match.group('var')} "
            ": eventRowsForOutput) {"
        ),
        func_body,
        count=1,
    )
    return prefix + func_body + rest


def _find_matching_brace_in_text(content: str, open_brace: int) -> int:
    if open_brace < 0 or open_brace >= len(content) or content[open_brace] != "{":
        return -1
    depth = 0
    for index in range(open_brace, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _ensure_output_manager_energy_deposit_event_fallback(content: str) -> str:
    if "eventRecordFallbackByEvent" in content:
        return content
    required_tokens = ("fEnergyDeposits", "fEventRecords")
    if not all(token in content for token in required_tokens):
        return content

    if "#include <utility>" not in content:
        content = _add_standard_include(content, "#include <utility>")
    event_table_fallback = (
        "    G4bool hasPositiveEventRecords = false;\n"
        "    for (const auto& rec : fEventRecords) {\n"
        "        if (rec.edep_MeV > 0.0 || rec.dose_Gy > 0.0) {\n"
        "            hasPositiveEventRecords = true;\n"
        "            break;\n"
        "        }\n"
        "    }\n"
        "    if (!hasPositiveEventRecords && !fEnergyDeposits.empty()) {\n"
        "        std::map<G4int, std::pair<G4double, G4double>> eventRecordFallbackByEvent;\n"
        "        G4int rowCount = fEventsRequested > 0 ? fEventsRequested : 0;\n"
        "        for (const auto& deposit : fEnergyDeposits) {\n"
        "            if (deposit.eventID >= rowCount) rowCount = deposit.eventID + 1;\n"
        "        }\n"
        "        for (G4int eventID = 0; eventID < rowCount; ++eventID) {\n"
        "            eventRecordFallbackByEvent[eventID] = {0.0, 0.0};\n"
        "        }\n"
        "        for (const auto& deposit : fEnergyDeposits) {\n"
        "            if (deposit.eventID < 0 || deposit.edep_MeV <= 0.0) continue;\n"
        "            auto& totals = eventRecordFallbackByEvent[deposit.eventID];\n"
        "            totals.first += deposit.edep_MeV;\n"
        "            totals.second += deposit.edep_MeV * 1.602176634e-13;\n"
        "        }\n"
        "        for (const auto& item : eventRecordFallbackByEvent) {\n"
        "            ofs << item.first << \",\"\n"
        "                << std::scientific << std::setprecision(6) << item.second.first << \",\"\n"
        "                << std::scientific << std::setprecision(6) << item.second.second << \"\\\\n\";\n"
        "        }\n"
        "        return;\n"
        "    }\n"
    )
    content = re.sub(
        r'(?P<header>[ \t]*ofs\s*<<\s*"EventID,edep_MeV,dose_Gy"\s*<<\s*"\\n"\s*;\s*)',
        r"\g<header>" + "\n" + event_table_fallback,
        content,
        count=1,
    )
    summary_preamble = (
        "    G4int eventRecordCountForSummary = static_cast<G4int>(fEventRecords.size());\n"
        "    G4bool hasPositiveEventRecordsForSummary = false;\n"
        "    for (const auto& rec : fEventRecords) {\n"
        "        if (rec.edep_MeV > 0.0 || rec.dose_Gy > 0.0) {\n"
        "            hasPositiveEventRecordsForSummary = true;\n"
        "            break;\n"
        "        }\n"
        "    }\n"
        "    if (!hasPositiveEventRecordsForSummary && !fEnergyDeposits.empty()) {\n"
        "        totalEdep = 0.0;\n"
        "        totalDose = 0.0;\n"
        "        G4int rowCount = fEventsRequested > 0 ? fEventsRequested : 0;\n"
        "        for (const auto& deposit : fEnergyDeposits) {\n"
        "            if (deposit.edep_MeV <= 0.0) continue;\n"
        "            totalEdep += deposit.edep_MeV;\n"
        "            totalDose += deposit.edep_MeV * 1.602176634e-13;\n"
        "            if (deposit.eventID >= rowCount) rowCount = deposit.eventID + 1;\n"
        "        }\n"
        "        eventRecordCountForSummary = rowCount;\n"
        "    }\n"
    )
    summary_pattern = (
        r"(?P<loop>[ \t]*for\s*\(\s*const\s+auto&\s+rec\s*:\s*fEventRecords\s*\)\s*\{\s*\n"
        r"[ \t]*totalEdep\s*\+=\s*rec\.edep_MeV\s*;\s*\n"
        r"[ \t]*totalDose\s*\+=\s*rec\.dose_Gy\s*;\s*\n"
        r"[ \t]*\}\s*)"
    )
    content = re.sub(summary_pattern, r"\g<loop>\n" + summary_preamble, content, count=1)
    summary_start = re.search(r"void\s+OutputManager::WriteSummaryJson\s*\(\s*\)", content)
    if summary_start:
        prefix = content[: summary_start.start()]
        suffix = content[summary_start.start() :]
        suffix = suffix.replace(
            "static_cast<G4int>(fEventRecords.size())",
            "eventRecordCountForSummary",
            1,
        )
        content = prefix + suffix
    return content


def _add_standard_include(content: str, include_line: str) -> str:
    if include_line in content:
        return content
    lines = content.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        if line.strip().startswith("#include "):
            insert_at = index + 1
            continue
        if insert_at:
            break
    lines.insert(insert_at, include_line)
    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline


def _insert_after_include_block(content: str, insertion: str) -> str:
    lines = content.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#include "):
            insert_at = index + 1
            continue
        if insert_at and stripped == "":
            insert_at = index + 1
            continue
        if insert_at:
            break
    if insert_at <= 0:
        return insertion + content
    lines.insert(insert_at, insertion.rstrip("\n"))
    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline


def _replace_shell_mkdir_with_filesystem(content: str) -> str:
    if "std::system" not in content and "mkdir -p" not in content:
        return content
    if "#include <filesystem>" not in content:
        if "#include <cstdlib>" in content:
            content = content.replace(
                "#include <cstdlib>",
                "#include <cstdlib>\n#include <filesystem>",
                1,
            )
        else:
            content = "#include <filesystem>\n" + content
    content = re.sub(
        r'\s*std::string\s+\w+\s*=\s*"mkdir -p "\s*\+\s*outDir;\n\s*std::system\(\w+\.c_str\(\)\);\n',
        "\n    std::filesystem::create_directories(outDir);\n",
        content,
        count=1,
    )
    return content


def _normalize_rotation_matrix_pointer_constness(content: str) -> str:
    if "const G4RotationMatrix*" not in content:
        return content
    return content.replace("const G4RotationMatrix*", "G4RotationMatrix*")


def _normalize_threadlocal_macro(content: str) -> str:
    if "G4THREADLOCAL" not in content:
        return content
    return content.replace("G4THREADLOCAL", "G4ThreadLocal")


def _normalize_vis_attributes_member_access(content: str) -> str:
    if "G4VisAttributes" not in content or "->" not in content:
        return content
    object_names = {
        match.group("name")
        for match in re.finditer(
            r"\bG4VisAttributes\s+(?P<name>[A-Za-z_]\w*)\s*\(",
            content,
        )
    }
    for name in sorted(object_names, key=len, reverse=True):
        content = re.sub(rf"\b{re.escape(name)}\s*->", f"{name}.", content)
    return content


def _ensure_required_geant4_includes(content: str) -> str:
    required: list[str] = []
    if "std::array" in content and "#include <array>" not in content:
        required.append("#include <array>")
    if "class G4RotationMatrix;" in content:
        content = re.sub(r"^\s*class\s+G4RotationMatrix\s*;\s*\n", "", content, flags=re.MULTILINE)
        if '#include "G4RotationMatrix.hh"' not in content:
            required.append('#include "G4RotationMatrix.hh"')
    if (
        re.search(r"(?<![:\w])(MeV|keV|eV|GeV|mm|cm|m|um|nm|s|ns|ms)\b", content)
        and '#include "G4SystemOfUnits.hh"' not in content
    ):
        required.append('#include "G4SystemOfUnits.hh"')
    if "G4RunManager::" in content and '#include "G4RunManager.hh"' not in content:
        required.append('#include "G4RunManager.hh"')
    if re.search(r"\bG4Event\b", content) and '#include "G4Event.hh"' not in content:
        required.append('#include "G4Event.hh"')
    if (
        "G4ParticleDefinition" in content
        and '#include "G4ParticleDefinition.hh"' not in content
    ):
        required.append('#include "G4ParticleDefinition.hh"')
    if "G4ParticleTable" in content and '#include "G4ParticleTable.hh"' not in content:
        required.append('#include "G4ParticleTable.hh"')
    if re.search(r"\bScoringManager\s*(?:::|\*)", content) and '#include "ScoringManager.hh"' not in content:
        required.append('#include "ScoringManager.hh"')
    if "G4Material" in content and '#include "G4Material.hh"' not in content:
        required.append('#include "G4Material.hh"')
    if "G4VSolid" in content and '#include "G4VSolid.hh"' not in content:
        required.append('#include "G4VSolid.hh"')
    if "BoundingLimits(" in content and '#include "G4VSolid.hh"' not in content:
        required.append('#include "G4VSolid.hh"')
    if "G4Colour" in content and '#include "G4Colour.hh"' not in content:
        required.append('#include "G4Colour.hh"')
    if "G4VisAttributes" in content and '#include "G4VisAttributes.hh"' not in content:
        required.append('#include "G4VisAttributes.hh"')
    if "G4ThreadLocal" in content and '#include "tls.hh"' not in content:
        required.append('#include "tls.hh"')
    if not required:
        return content

    lines = content.splitlines()
    insert_at = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#include "):
            insert_at = index + 1
            continue
        if stripped == "" and insert_at == index:
            insert_at = index + 1
            continue
        if insert_at:
            break

    for include in reversed(required):
        lines.insert(insert_at, include)
    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(lines) + trailing_newline


def _normalize_macro_cut_commands(content: str) -> str:
    lines = content.splitlines()
    normalized: list[str] = []
    inserted_default_cut = False
    removed_any = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("/run/setCutForGamma", "/run/setCutForElectron", "/run/setCutForPositron")):
            removed_any = True
            if not inserted_default_cut and "/run/setCut " not in content:
                normalized.append("/run/setCut 0.1 mm")
                inserted_default_cut = True
            continue
        normalized.append(line)
    if not removed_any:
        return content
    trailing_newline = "\n" if content.endswith("\n") else ""
    return "\n".join(normalized) + trailing_newline


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
        issues.extend(_find_include_inside_function(file_entry))
        issues.extend(_find_placeholder_event_track_ids(file_entry))
        issues.extend(_find_unqualified_hit_allocations(file_entry))
        if len(issues) >= 12:
            return issues[:12]
    issues.extend(_find_sensitive_detector_constructor_mismatches(generated_files))
    if len(issues) >= 12:
        return issues[:12]
    issues.extend(_find_unwired_runtime_output_manager_flow(generated_files))
    if len(issues) >= 12:
        return issues[:12]
    return issues


def _critical_generated_content_errors(issues: list[str]) -> list[str]:
    critical_markers = (
        "include inside function body",
        "placeholder event/track id",
        "unqualified Hit allocation",
        "SensitiveDetector constructor argument mismatch",
        "runtime OutputManager data flow not wired",
    )
    return [
        f"critical generated content issue: {issue}"
        for issue in issues
        if any(marker in issue for marker in critical_markers)
    ]


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


def _find_include_inside_function(file_entry: GeneratedModuleFile) -> list[str]:
    issues: list[str] = []
    depth = 0
    for line_no, line in enumerate(file_entry.new_content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#include") and depth > 0:
            issues.append(
                f"{file_entry.path}: include inside function body at line {line_no}: {stripped}"
            )
        depth += line.count("{") - line.count("}")
    return issues


def _find_placeholder_event_track_ids(file_entry: GeneratedModuleFile) -> list[str]:
    patterns = (
        re.compile(r"\bSetEventID\s*\(\s*0\s*\)", re.IGNORECASE),
        re.compile(r"\bSetTrackID\s*\(\s*0\s*\)", re.IGNORECASE),
        re.compile(r"\bevent_id\s*[:=]\s*0\b", re.IGNORECASE),
        re.compile(r"\btrack_id\s*[:=]\s*0\b", re.IGNORECASE),
    )
    issues: list[str] = []
    for line_no, line in enumerate(file_entry.new_content.splitlines(), start=1):
        lowered = line.lower()
        explicit_zero_id = any(pattern.search(line) for pattern in patterns)
        placeholder_comment = (
            "placeholder" in lowered
            and ("event" in lowered or "track" in lowered)
            and "not a placeholder" not in lowered
            and "no placeholder" not in lowered
            and "without placeholder" not in lowered
        )
        if explicit_zero_id or placeholder_comment:
            snippet = line.strip()
            if len(snippet) > 240:
                snippet = snippet[:237] + "..."
            issues.append(
                f"{file_entry.path}: placeholder event/track id at line {line_no}: {snippet}"
            )
    return issues


def _find_unqualified_hit_allocations(file_entry: GeneratedModuleFile) -> list[str]:
    if file_entry.path != "src/SensitiveDetector.cc":
        return []
    pattern = re.compile(r"\bnew\s+Hit\s*\(")
    issues: list[str] = []
    in_block_comment = False
    for line_no, line in enumerate(file_entry.new_content.splitlines(), start=1):
        code_line, in_block_comment = _strip_cpp_comments_from_line(
            line,
            in_block_comment=in_block_comment,
        )
        if not pattern.search(code_line):
            continue
        snippet = line.strip()
        issues.append(
            f"{file_entry.path}: unqualified Hit allocation at line {line_no}: "
            f"{snippet}; use new ::Hit() inside G4VSensitiveDetector subclasses"
        )
    return issues


def _strip_cpp_comments_from_line(line: str, *, in_block_comment: bool) -> tuple[str, bool]:
    result: list[str] = []
    index = 0
    while index < len(line):
        if in_block_comment:
            end = line.find("*/", index)
            if end < 0:
                return "".join(result), True
            index = end + 2
            in_block_comment = False
            continue
        line_comment = line.find("//", index)
        block_comment = line.find("/*", index)
        if line_comment >= 0 and (block_comment < 0 or line_comment < block_comment):
            result.append(line[index:line_comment])
            return "".join(result), False
        if block_comment >= 0:
            result.append(line[index:block_comment])
            index = block_comment + 2
            in_block_comment = True
            continue
        result.append(line[index:])
        break
    return "".join(result), in_block_comment


def _find_sensitive_detector_constructor_mismatches(
    generated_files: list[GeneratedModuleFile],
) -> list[str]:
    by_path = {entry.path: entry.new_content for entry in generated_files}
    header = by_path.get("include/SensitiveDetector.hh", "")
    if not header:
        return []
    expected = _sensitive_detector_constructor_arg_count(header)
    if not expected:
        return []

    issues: list[str] = []
    for entry in generated_files:
        for line_no, call_args in _sensitive_detector_constructor_calls(entry.new_content):
            observed = _argument_count(call_args)
            if observed != expected:
                issues.append(
                    f"{entry.path}: SensitiveDetector constructor argument mismatch "
                    f"at line {line_no}: expected {expected}, found {observed}"
                )
    return issues


def _find_unwired_runtime_output_manager_flow(
    generated_files: list[GeneratedModuleFile],
) -> list[str]:
    by_path = {entry.path: entry.new_content for entry in generated_files}
    output_header = by_path.get("include/OutputManager.hh", "")
    stepping_header = by_path.get("include/SteppingAction.hh", "")
    stepping_source = by_path.get("src/SteppingAction.cc", "")
    action_source = by_path.get("src/ActionInitialization.cc", "")
    if not output_header or not stepping_source:
        return []

    exposes_step_artifact_api = (
        "AddEnergyDepositPoint" in output_header
        or "RecordEnergyDeposit" in output_header
        or "Record3DHit" in output_header
    ) and (
        "AddTrackPoint" in output_header
        or "RecordTrack" in output_header
        or "RecordStep" in output_header
    )
    if not exposes_step_artifact_api:
        return []

    has_output_member = "OutputManager*" in stepping_header or "OutputManager*" in stepping_source
    records_energy_points = (
        "AddEnergyDepositPoint" in stepping_source
        or "RecordEnergyDeposit" in stepping_source
        or "Record3DHit" in stepping_source
    )
    records_track_points = (
        "AddTrackPoint" in stepping_source
        or "RecordTrack" in stepping_source
        or "RecordStep" in stepping_source
    )
    action_passes_output = bool(
        re.search(
            r"new\s+SteppingAction\s*\([^;]*fOutputManager",
            action_source,
            flags=re.DOTALL,
        )
        or re.search(
            r"new\s+SteppingAction\s*\([^;]*outputManager",
            action_source,
            flags=re.DOTALL | re.IGNORECASE,
        )
    )
    if has_output_member and records_energy_points and records_track_points and action_passes_output:
        return []

    missing: list[str] = []
    if not has_output_member:
        missing.append("SteppingAction OutputManager* dependency")
    if not records_energy_points:
        missing.append("SteppingAction energy deposit recording")
    if not records_track_points:
        missing.append("SteppingAction track point recording")
    if not action_passes_output:
        missing.append("ActionInitialization passes OutputManager to SteppingAction")
    return [
        "runtime_app: runtime OutputManager data flow not wired: "
        + ", ".join(missing)
    ]


def _sensitive_detector_constructor_arg_count(header: str) -> int:
    counts: list[int] = []
    for match in re.finditer(
        r"SensitiveDetector\s*\((?P<args>[^;{}]*)\)\s*(?:=\s*delete\s*)?;",
        header,
        re.DOTALL,
    ):
        args = match.group("args")
        if _is_copy_or_move_constructor_args(args):
            continue
        counts.append(_argument_count(args))
    return max(counts, default=0)


def _is_copy_or_move_constructor_args(args: str) -> bool:
    normalized = re.sub(r"\s+", " ", args.strip())
    return bool(
        re.fullmatch(
            r"(?:const\s+)?SensitiveDetector\s*(?:&&|&)(?:\s+\w+)?",
            normalized,
        )
    )


def _sensitive_detector_constructor_calls(content: str) -> list[tuple[int, str]]:
    calls: list[tuple[int, str]] = []
    pattern = re.compile(r"new\s+SensitiveDetector\s*\(")
    lines = content.splitlines()
    for index, line in enumerate(lines, start=1):
        match = pattern.search(line)
        if not match:
            continue
        tail = line[match.end():]
        if ")" in tail:
            calls.append((index, tail.split(")", 1)[0]))
            continue
        parts = [tail]
        for extra in lines[index:]:
            if ")" in extra:
                parts.append(extra.split(")", 1)[0])
                break
            parts.append(extra)
        calls.append((index, "\n".join(parts)))
    return calls


def _argument_count(args: str) -> int:
    text = args.strip()
    if not text or text == "void":
        return 0
    depth = 0
    count = 1
    for char in text:
        if char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            count += 1
    return count


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
