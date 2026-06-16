"""Full-project agentic Geant4 code generation.

This path gives one tool-using agent ownership of the whole Geant4 project
workspace. It replaces the default split-module writing path for production
codegen while keeping the same downstream patch/report contracts.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from agent_core.agent_loop import run_agent_loop
from agent_core.dev_tools import DevToolkit
from agent_core.g4_codegen.agentic_repair import (
    _Geant4RepairToolkit,
    _build_continuation_request,
    _collect_errors,
    _reconstruct_patch_from_project,
)
from agent_core.g4_codegen.template_project import create_minimal_geant4_project
from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import GEANT4_PROJECT_DIRNAME, STAGE_CODEGEN

DEFAULT_PROJECT_AGENT_MAX_TURNS = 64
PROJECT_AGENT_WORKSPACE = Path(STAGE_CODEGEN) / "project_agent" / GEANT4_PROJECT_DIRNAME

GEANT4_PROJECT_AGENT_SYSTEM_PROMPT = """\
你是 RadAgent 的 Geant4 全工程编码 Agent，工作方式类似 Claude Code/Codex：
直接在一个真实 Geant4 项目目录中读文件、写文件、编译、运行 smoke，再根据终端反馈继续修。

你不是分模块 JSON 生成器。你拥有整个工程：
- geometry/materials/placement
- source/physics list
- sensitive detector/scoring
- runtime actions/output manager
- main.cc/CMakeLists.txt/macros

工具：
- list_files(glob?): 查项目文件。
- read_file(path): 读取真实文件，带行号。
- search_text(pattern, glob?): 在项目内找符号、构造函数、方法、placeholder。
- search_geant4_docs(query): 查 Geant4 官方 API/示例；不确定签名、宏命令或物理列表 API 时先查。
- search_web(query): 查公开 Web；当项目文件和本地 Geant4 RAG 仍不足以判断 API/报错时使用。
- write_file(path, content): 写完整文件。
- edit_file(path, old_string, new_string): 精确替换唯一片段。
- build_project(): cmake + make，输出完整编译错误；这是你的 ground truth。
- run_smoke(events?): build + 小事件运行，并检查输出合同。

硬规则：
1. 先用 list_files/read_file 理解 canonical template 的真实接口，再改文件；不要凭记忆重造 B1 骨架。
2. 任何跨类调用都以当前 include/*.hh 为准。若 main.cc 调用 PhysicsListFactoryWrapper，
   先读 include/PhysicsListFactoryWrapper.hh，再按真实返回类型 wiring；不要 dynamic_cast 一个
   非多态 wrapper。
3. 每批写完一组相关文件后必须 build_project。不要连续大量 read/search 而不编译。
4. build_project 失败时，按同一次编译输出分组修完所有独立错误，再 rebuild。
5. build 通过后必须 run_smoke。run_smoke 通过才算完成。
6. smoke 输出合同是硬要求，所有文件必须写入 G4_OUTPUT_DIR：
   g4_summary.json、provenance.json、event_table.csv、edep_3d.csv、dose_3d.csv、
   geometry_view.json、particle_tracks.json、energy_deposits.json。
7. artifact 数据必须来自真实 Geant4 event/track/step/hit 数据路径；不得留 TODO/stub/dummy/placeholder。
8. 包裹/屏蔽几何不能作为同级实心重叠体放置；用 shell/boolean subtraction 或 mother-daughter。
9. voxel/bin 分配必须有每轴上限，避免 cm 级体积使用 10 um 默认导致 std::length_error。
10. 不要新增 shell 脚本、CMakePresets 或修改项目外文件。只改当前 Geant4 project 目录内源码/宏/配置。

结束条件：
- run_smoke 工具返回 ok=true 后，回复 exactly: BUILD AND SMOKE PASSED
"""


async def run_geant4_project_agent(
    *,
    job_id: str,
    g4_model_ir: dict[str, Any] | None = None,
    codegen_plan: dict[str, Any] | None = None,
    geometry_strategy_plan: dict[str, Any] | None = None,
    code_architecture_plan: dict[str, Any] | None = None,
    module_contracts: dict[str, Any] | None = None,
    module_contexts: dict[str, Any] | None = None,
    interface_contracts: dict[str, Any] | None = None,
    runtime_failure_context: dict[str, Any] | None = None,
    seed_patch: dict[str, Any] | None = None,
    expected_events: int = 100,
    max_turns: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate and verify a complete Geant4 project in one agentic loop."""
    project_dir = get_job_dir(job_id) / PROJECT_AGENT_WORKSPACE
    _reset_project_workspace(
        project_dir,
        expected_events=expected_events,
        seed_patch=seed_patch,
    )

    toolkit = _Geant4RepairToolkit(
        project_dir,
        job_id=job_id,
        tool_names=[
            "list_files",
            "search_text",
            "search_geant4_docs",
            "search_web",
            "read_file",
            "edit_file",
            "write_file",
            "build_project",
            "run_smoke",
        ],
    )
    gateway = get_model_gateway()
    user_message = _build_project_user_message(
        job_id=job_id,
        g4_model_ir=g4_model_ir or {},
        codegen_plan=codegen_plan or {},
        geometry_strategy_plan=geometry_strategy_plan or {},
        code_architecture_plan=code_architecture_plan or {},
        module_contracts=module_contracts or {},
        module_contexts=module_contexts or {},
        interface_contracts=interface_contracts or {},
        runtime_failure_context=runtime_failure_context or {},
        expected_events=expected_events,
    )

    budget = max_turns or _positive_int(
        os.getenv("RADAGENT_PROJECT_AGENT_MAX_TURNS"),
        DEFAULT_PROJECT_AGENT_MAX_TURNS,
    )
    history_chars = _optional_positive_int(os.getenv("RADAGENT_PROJECT_AGENT_HISTORY_CHARS"))

    loop_result = await run_agent_loop(
        gateway=gateway,
        task=ModelTask.CODEGEN,
        tier=ModelTier.PRO,
        system_prompt=GEANT4_PROJECT_AGENT_SYSTEM_PROMPT,
        user_message=user_message,
        toolkit=toolkit,
        max_turns=budget,
        max_tokens=16384,
        stop_hook=_smoke_passed,
        nudge_hook=_project_agent_nudge,
        metadata={
            "job_id": job_id,
            "module_name": "geant4_project_agent",
            "enable_thinking": True,
            "agentic_project_codegen": True,
        },
        max_stalls=8,
        repeated_tool_result_limit=3,
        max_history_chars=history_chars,
        preserve_recent_tool_messages=3,
        stall_nudge=(
            "The project is not verified yet. Use the latest build_project or "
            "run_smoke output to choose the next smallest edit. If you are unsure "
            "about a Geant4 API or macro command, call search_geant4_docs or "
            "search_web when local docs are insufficient. Then "
            "edit/write the relevant file and verify with build_project. If build "
            "passes, call run_smoke."
        ),
    )

    patch = _build_project_patch(project_dir, job_id)
    from agent_core.g4_codegen.global_integration_agent import (
        _final_runtime_gate_metadata,
        _run_integration_runtime_gate,
    )

    gate = await _run_integration_runtime_gate(
        job_id=job_id,
        proposed_patch=patch,
        attempt=0,
        expected_events=expected_events,
    )
    status = "passed" if gate.get("status") == "pass" else "failed"
    report = _build_project_report(
        job_id=job_id,
        status=status,
        patch=patch,
        gate=gate,
        loop_result=loop_result,
    )
    continuation_request = _build_continuation_request(loop_result, gate)
    if continuation_request:
        report["continuation_request"] = continuation_request

    patch.setdefault("metadata", {})
    patch["metadata"]["source"] = "geant4_project_agent"
    patch["metadata"]["global_integration_agent"] = {
        "status": status,
        "issues_fixed": 0,
        "changed_files": len(patch.get("changed_files", [])),
        "report_path": f"{STAGE_CODEGEN}/global_integration_agent_report.json",
        "runtime_gate_required": True,
        "agent_name": "geant4_project_agent",
    }
    patch["metadata"]["final_runtime_gate"] = _final_runtime_gate_metadata(expected_events)
    _persist_patch_and_report(patch, report, job_id)
    return patch, report


async def geant4_project_agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """Graph node wrapper for full-project agentic codegen."""
    from agent_core.tools.geant4_workbench import resolve_self_check_events

    job_id = state.get("job_id", "unknown")
    expected_events = resolve_self_check_events(g4_model_ir=state.get("g4_model_ir", {}))
    seed_patch = state.get("proposed_patch") if _is_project_agent_reentry(state) else None
    patch, report = await run_geant4_project_agent(
        job_id=job_id,
        g4_model_ir=state.get("g4_model_ir", {}),
        codegen_plan=state.get("codegen_plan", {}),
        geometry_strategy_plan=state.get("geometry_strategy_plan", {}),
        code_architecture_plan=state.get("code_architecture_plan", {}),
        module_contracts=state.get("module_contracts", {}),
        module_contexts=state.get("module_contexts", {}),
        interface_contracts=state.get("interface_contracts", {}),
        runtime_failure_context=state.get("runtime_failure_context", {}),
        seed_patch=seed_patch,
        expected_events=expected_events,
        max_turns=_agentic_max_turns_override(state),
    )
    return {
        "proposed_patch": patch,
        "global_integration_agent_report": report,
        "current_node": "geant4_project_agent",
        "codegen_errors": list(state.get("codegen_errors", [])) + report.get("errors", []),
        "runtime_execution_audit": {},
        "physics_quality_review": {},
    }


def _is_project_agent_reentry(state: dict[str, Any]) -> bool:
    proposed_patch = state.get("proposed_patch")
    if not isinstance(proposed_patch, dict) or not proposed_patch.get("changed_files"):
        return False
    return bool(
        state.get("runtime_failure_context")
        or state.get("runtime_execution_audit")
        or state.get("physics_quality_review")
        or state.get("runtime_audit_repair_attempts")
        or state.get("physics_review_repair_attempts")
    )


async def _smoke_passed(_toolkit: DevToolkit, audit: list[dict[str, Any]]) -> bool:
    for entry in reversed(audit):
        if entry.get("name") == "run_smoke":
            return bool(entry.get("ok"))
    return False


def _project_agent_nudge(audit: list[dict[str, Any]]) -> str | None:
    if not audit:
        return None
    recent = audit[-4:]
    read_only = {"read_file", "list_files", "search_text", "search_geant4_docs", "search_web"}
    if len(recent) >= 4 and all(str(entry.get("name")) in read_only for entry in recent):
        return (
            "You have spent several tool calls investigating. Make a concrete "
            "write_file/edit_file change now, then call build_project."
        )
    last_build_or_smoke = next(
        (
            entry
            for entry in reversed(audit)
            if entry.get("name") in {"build_project", "run_smoke"}
        ),
        None,
    )
    if (
        last_build_or_smoke
        and not last_build_or_smoke.get("ok")
        and not any(entry.get("name") in {"edit_file", "write_file"} for entry in recent)
    ):
        return (
            "The latest verification failed and no edit has followed it. Fix the "
            "file named in that output, then call build_project again."
        )
    return None


def _reset_project_workspace(
    project_dir: Path,
    *,
    expected_events: int,
    seed_patch: dict[str, Any] | None = None,
) -> None:
    if project_dir.exists():
        shutil.rmtree(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    create_minimal_geant4_project(project_dir, events=expected_events)
    if seed_patch:
        _overlay_patch_files(project_dir, seed_patch)


def _overlay_patch_files(project_dir: Path, patch: dict[str, Any]) -> None:
    """Seed the project workspace from a previous proposed patch."""
    for entry in patch.get("changed_files", []) or []:
        if not isinstance(entry, dict):
            continue
        rel_path = str(entry.get("path") or "")
        content = entry.get("new_content")
        if not rel_path or content is None:
            continue
        if rel_path.startswith("/") or ".." in Path(rel_path).parts:
            continue
        target = project_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")


def _build_project_patch(project_dir: Path, job_id: str) -> dict[str, Any]:
    patch = _reconstruct_patch_from_project(
        project_dir,
        {
            "patch_id": f"patch_{job_id}_g4_project_agent",
            "job_id": job_id,
            "description": "Agent-generated full Geant4 project",
            "change_type": "create_or_replace",
            "risk_level": "medium",
            "patch_type": "json_file_replacement",
            "changed_files": [],
            "test_plan": [
                "Build with Geant4Runner.smoke_test",
                "Run smoke simulation and verify output contract artifacts",
            ],
            "expected_outputs": [
                "Complete geant4_project source tree",
                "Required RadAgent Geant4 output contract files",
            ],
            "metadata": {"source": "geant4_project_agent"},
        },
    )
    patch.setdefault("patch_id", f"patch_{job_id}_g4_project_agent")
    patch.setdefault("job_id", job_id)
    patch.setdefault("description", "Agent-generated full Geant4 project")
    patch.setdefault("change_type", "create_or_replace")
    patch.setdefault("risk_level", "medium")
    patch.setdefault("patch_type", "json_file_replacement")
    patch.setdefault("test_plan", ["Run Geant4 smoke test"])
    patch.setdefault("expected_outputs", ["Complete Geant4 project"])
    patch.setdefault("metadata", {})
    patch["metadata"]["source"] = "geant4_project_agent"
    return patch


def _build_project_report(
    *,
    job_id: str,
    status: str,
    patch: dict[str, Any],
    gate: dict[str, Any],
    loop_result: Any,
) -> dict[str, Any]:
    errors = [] if status == "passed" else _collect_errors(gate, loop_result)
    return {
        "job_id": job_id,
        "status": status,
        "agent_name": "geant4_project_agent",
        "issues_fixed": [],
        "changed_files": [entry.get("path") for entry in patch.get("changed_files", [])],
        "errors": errors,
        "runtime_gate_attempts": [gate],
        "capabilities_used": {
            "read_project_files": True,
            "database_search": True,
            "web_search": _tool_used(loop_result, "search_web"),
            "write_proposed_patch": True,
            "build_project": True,
            "run_smoke": True,
        },
        "agentic": {
            "stop_reason": getattr(loop_result, "stop_reason", None),
            "n_turns": getattr(loop_result, "n_turns", None),
            "tool_calls": len(getattr(loop_result, "tool_audit", []) or []),
            "tool_audit": _slim_audit(getattr(loop_result, "tool_audit", []) or []),
        },
    }


def _build_project_user_message(
    *,
    job_id: str,
    g4_model_ir: dict[str, Any],
    codegen_plan: dict[str, Any],
    geometry_strategy_plan: dict[str, Any],
    code_architecture_plan: dict[str, Any],
    module_contracts: dict[str, Any],
    module_contexts: dict[str, Any],
    interface_contracts: dict[str, Any],
    runtime_failure_context: dict[str, Any],
    expected_events: int,
) -> str:
    context = {
        "job_id": job_id,
        "expected_smoke_events": expected_events,
        "g4_model_ir": g4_model_ir,
        "codegen_plan": codegen_plan,
        "geometry_strategy_plan": geometry_strategy_plan,
        "code_architecture_plan": code_architecture_plan,
        "module_contracts_as_responsibility_hints": module_contracts,
        "module_contexts_with_hard_constraints": _compact_module_contexts_for_project_agent(
            module_contexts
        ),
        "interface_contracts": interface_contracts,
        "runtime_failure_context": runtime_failure_context,
    }
    return (
        "Generate a complete Geant4 project for the following RadAgent model IR. "
        "The project directory already contains a canonical template; inspect and "
        "modify it instead of starting from scattered snippets. Build and smoke-run "
        "the result with tools.\n\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2, default=str)}"
    )


def _compact_module_contexts_for_project_agent(module_contexts: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for module_name, ctx in module_contexts.items():
        if not isinstance(ctx, dict):
            continue
        compact[str(module_name)] = {
            key: value
            for key, value in ctx.items()
            if key
            in {
                "module_name",
                "module_contract",
                "human_confirmation_context",
                "agentic_repair_lessons",
                "context_retrieval_policy",
                "rag_snippets",
                "web_context",
            }
        }
    return compact

def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _tool_used(loop_result: Any, tool_name: str) -> bool:
    return any(
        isinstance(entry, dict) and entry.get("name") == tool_name
        for entry in (getattr(loop_result, "tool_audit", []) or [])
    )


def _agentic_max_turns_override(state: dict[str, Any]) -> int | None:
    try:
        value = int(state.get("agentic_repair_max_turns_override") or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _slim_audit(audit: list[dict[str, Any]]) -> list[dict[str, Any]]:
    slimmed: list[dict[str, Any]] = []
    for entry in audit:
        result = entry.get("result") if isinstance(entry.get("result"), dict) else {}
        slimmed.append(
            {
                "turn": entry.get("turn"),
                "name": entry.get("name"),
                "ok": entry.get("ok"),
                "exit_code": result.get("exit_code"),
                "stage": result.get("stage"),
            }
        )
    return slimmed


def _persist_patch_and_report(
    patch: dict[str, Any],
    report: dict[str, Any],
    job_id: str,
) -> None:
    from agent_core.g4_codegen.global_integration_agent import _persist_report

    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)
    (codegen_dir / "proposed_patch.json").write_text(
        json.dumps(patch, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    summary = {
        "patch_type": patch.get("patch_type"),
        "total_files": len(patch.get("changed_files", [])),
        "metadata": patch.get("metadata", {}),
    }
    (codegen_dir / "proposed_patch_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _persist_report(report, job_id)
