"""LLM physics quality reviewer for generated Geant4 projects."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from agent_core.models.gateway import _safe_parse_json, get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier
from agent_core.workspace.io import get_job_dir
from agent_core.workspace.paths import STAGE_CODEGEN

MAX_REVIEW_CONTEXT_CHARS = 45_000
PROJECT_FILE_REVIEW_CHARS = 16_000
PROJECT_FILE_REVIEW_CHARS_PER_FILE = 3_200
REVIEW_SOURCE_KEYWORDS = (
    "SetParticle",
    "GeneratePrimaries",
    "ParticleGun",
    "FindParticle",
    "SetParticleEnergy",
    "SetParticlePosition",
    "SetParticleMomentumDirection",
    "FTFP_BERT",
    "PhysicsList",
    "production",
    "cut",
    "step",
    "G4Box",
    "G4Tubs",
    "G4PVPlacement",
    "FindOrBuildMaterial",
    "G4_Si",
    "G4_Al",
    "G4_AIR",
    "SensitiveDetector",
    "Scoring",
    "edep",
    "dose",
    "EventID",
    "WriteEventTable",
    "WriteEdep3D",
    "WriteDose3D",
    "WriteGeometryViewJson",
    "WriteParticleTracksJson",
    "WriteEnergyDepositsJson",
    "AddTrackPoint",
    "AddEnergyDepositPoint",
)

PHYSICS_REVIEW_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 物理质量审核 Agent。

你不写代码。你负责审核最终 Geant4 工程是否忠实满足原始 G4ModelIR 和用户需求。
重点关注：
1. 物理模型/physics list 是否适合粒子、能量、材料和 scoring 目标。
2. 粒子源是否忠实保留粒子类型、能量、方向、位置、空间分布和单位。
3. 对复合辐射场，必须审核 all G4ModelIR sources；不得只看第一个 source。逐项核验
   每个 source 的 spectrum、angular_distribution、events 和 relative_weight 是否保留。
4. 几何、材料、敏感体和 scoring 是否被擅自简化。
5. transport precision 是否足够，包括 production cuts、range cuts、step limits、
   user limits、最小步长或等效控制是否合理。
6. 输出 artifact 是否代表真实 event/scoring 数据，而不是表头、固定零值或 fallback 假数据。
7. 如果使用 Geant4 示例代码，是否只是参考真实接口，而不是把 B1/B2 示例需求照搬进当前需求。
8. 如果 runtime_verification_summary 显示最新 runtime gate 已通过，必须把该最新通过事实
   作为 runtime/build/artifact 状态的权威证据；不得因为早期 repair attempt 的旧失败
   要求已经被最新通过结果否定的修复。仍可基于当前 project_files 和 G4ModelIR 提出
   未被 runtime pass 覆盖的真实物理保真度问题。

只返回 JSON，不要输出 Markdown fence。

返回格式：
{
  "status": "pass" | "revise" | "needs_user_input" | "fail",
  "routing_recommendation": "accept" | "repair_code" | "request_user_input" | "fail",
  "overall_score": 0,
  "physics_model_score": 0,
  "source_fidelity_score": 0,
  "geometry_fidelity_score": 0,
  "transport_precision_score": 0,
  "output_validity_score": 0,
  "findings": [{"severity": "low|medium|high", "target": "...", "message": "..."}],
  "required_fixes": [{"target": "...", "message": "..."}],
  "needs_user_input": [{"target": "...", "message": "..."}],
  "advisory_findings": [{"severity": "low|medium|high", "target": "...", "message": "..."}],
  "reviewer_notes": "..."
}

硬性分类规则：
- required_fixes 只能包含 Geant4 工程 Agent 能通过编辑项目文件直接修复的问题。
- 不要把“获取用户确认”“确认材料/几何选择”“confirmed_by_user=false”
  “requires_confirmation=true”“修改/澄清 G4ModelIR metadata”放进 required_fixes。
  这些属于上游建模确认缺口，只能放入 needs_user_input 或 advisory_findings。
- 如果 G4ModelIR 自身矛盾，且需要在人类选择后才能知道正确材料、几何或 scoring，
  返回 status="needs_user_input"、routing_recommendation="request_user_input"。
- 这是 codegen 之后的审核阶段，禁止向用户发起新的人工确认流程；确认材料、几何、
  physics cuts、scoring 语义等问题必须在 codegen 前的 human_confirmation 阶段完成。
  因此这里的 needs_user_input 只表示“上游确认缺口/流程失败”，不会被路由到用户确认。
- 如果最新 runtime gate 已通过，且 deterministic output_quality 已通过，
  event_table 额外列、大小写列名、附加 CSV 是否写入 IR 这类格式偏好默认放入
  advisory_findings；除非缺少真实用户要求的物理量或 artifact 是空/假/固定值。
- 如果所有阻塞项都需要用户或上游 IR 澄清，required_fixes 必须为空。
"""


async def run_physics_quality_reviewer(
    *,
    proposed_patch: dict[str, Any],
    g4_model_ir: dict[str, Any],
    module_contracts: dict[str, Any],
    module_contexts: dict[str, Any],
    global_integration_report: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """Review generated Geant4 physics/modeling fidelity with an LLM."""
    context = {
        "job_id": job_id,
        "g4_model_ir": _g4_model_ir_for_review(g4_model_ir),
        "module_contracts": _compact_module_contracts(module_contracts),
        "module_context_summaries": _compact_module_contexts(module_contexts),
        "global_integration_report": _global_integration_report_for_review(
            global_integration_report
        ),
        "runtime_verification_summary": _runtime_verification_summary(
            global_integration_report
        ),
        "project_files": _project_files_for_review(
            proposed_patch,
            max_total_chars=PROJECT_FILE_REVIEW_CHARS,
            max_chars_per_file=PROJECT_FILE_REVIEW_CHARS_PER_FILE,
        ),
        "review_instruction": (
            "Score physics/model/source/geometry/transport/output fidelity. "
            "If runtime_verification_summary.latest_runtime_gate_passed is true, "
            "treat the latest passing runtime gate as authoritative for build/run/"
            "artifact status and do not request fixes solely from earlier failed "
            "runtime attempts. "
            "When status is revise or fail, required_fixes must contain ONLY "
            "code-repairable issues that the Geant4 project agent can fix by "
            "editing project files. This is a post-codegen review, so never ask "
            "the user to confirm parameters here. Put upstream G4ModelIR "
            "clarification/metadata gaps into needs_user_input as a workflow "
            "contract failure, and put nonblocking output-format preferences into "
            "advisory_findings."
        ),
    }
    prompt = _review_prompt_json(context, max_chars=MAX_REVIEW_CONTEXT_CHARS)

    gateway = get_model_gateway()
    result = await gateway.call(
        task=ModelTask.CONTEXT_SUMMARY,
        tier=ModelTier.LITE,
        system_prompt=PHYSICS_REVIEW_SYSTEM_PROMPT,
        user_prompt=prompt,
        response_format="json",
        max_tokens=4096,
        metadata={
            "job_id": job_id,
            "module_name": "physics_quality_reviewer",
            "enable_thinking": False,
        },
    )

    if result.error:
        review = {
            "status": "fail",
            "overall_score": 0,
            "errors": [f"Physics quality reviewer model call failed: {result.error}"],
            "required_fixes": [
                {
                    "target": "physics_quality_review",
                    "message": (
                        "Reviewer model call failed; generated physics fidelity "
                        "was not verified."
                    ),
                }
            ],
            "summary_model": _model_info(result),
        }
        _persist_review(review, job_id)
        return review

    data = result.parsed_json or _safe_parse_json(result.content) or {}
    review = _normalize_review(data)
    review["summary_model"] = _model_info(result)
    _persist_review(review, job_id)
    return review


def physics_review_to_runtime_observation(review: dict[str, Any]) -> dict[str, Any]:
    """Convert revise/fail review output into global integration observation."""
    required_fixes = review.get("required_fixes", [])
    errors: list[str] = []
    if isinstance(required_fixes, list):
        for fix in required_fixes:
            if isinstance(fix, dict):
                target = fix.get("target", "physics_review")
                message = fix.get("message", "")
                errors.append(f"{target}: {message}")
    if not errors:
        errors = ["Physics quality reviewer requested revision without concrete fixes"]
    return {
        "status": "fail",
        "phase": "physics_quality_review",
        "errors": errors,
        "details": {
            "physics_quality_review": review,
            "failed_gates": [
                {
                    "gate_id": "physics_quality_review",
                    "name": "LLM physics fidelity review",
                    "status": review.get("status", "fail"),
                    "failed_items": errors,
                    "message": "Physics reviewer found modeling fidelity issues.",
                }
            ],
        },
    }


def _normalize_review(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    status = str(data.get("status", "fail")).strip().lower()
    if status not in {"pass", "revise", "needs_user_input", "fail"}:
        status = "fail"
    required_fixes = _list_of_dicts(data.get("required_fixes", []))
    explicit_needs_user_input = _list_of_dicts(data.get("needs_user_input", []))
    explicit_advisory = _list_of_dicts(data.get("advisory_findings", []))
    classified = _classify_required_fixes(
        required_fixes,
        needs_user_input=explicit_needs_user_input,
        advisory_findings=explicit_advisory,
    )
    routing = _normalize_routing_recommendation(
        data.get("routing_recommendation"),
        status=status,
        required_fixes=classified["required_fixes"],
        needs_user_input=classified["needs_user_input"],
    )
    if routing == "request_user_input" and not classified["required_fixes"]:
        status = "needs_user_input"
    elif routing == "repair_code" and status == "needs_user_input":
        status = "revise"
    elif routing == "accept":
        status = "pass"
    review: dict[str, Any] = {
        "status": status,
        "routing_recommendation": routing,
        "overall_score": _score(data.get("overall_score")),
        "physics_model_score": _score(data.get("physics_model_score")),
        "source_fidelity_score": _score(data.get("source_fidelity_score")),
        "geometry_fidelity_score": _score(data.get("geometry_fidelity_score")),
        "transport_precision_score": _score(data.get("transport_precision_score")),
        "output_validity_score": _score(data.get("output_validity_score")),
        "findings": _list_of_dicts(data.get("findings", [])),
        "required_fixes": classified["required_fixes"],
        "needs_user_input": classified["needs_user_input"],
        "advisory_findings": classified["advisory_findings"],
        "reviewer_notes": str(data.get("reviewer_notes", "")),
    }
    if status in {"revise", "fail"} and not review["required_fixes"]:
        if review["needs_user_input"]:
            review["status"] = "needs_user_input"
            review["routing_recommendation"] = "request_user_input"
        else:
            review["required_fixes"] = [
                {
                    "target": "physics_quality_review",
                    "message": (
                        "Reviewer did not provide concrete fixes; rerun review or "
                        "inspect findings."
                    ),
                }
            ]
            review["routing_recommendation"] = "repair_code"
    return review


def _classify_required_fixes(
    required_fixes: list[dict[str, Any]],
    *,
    needs_user_input: list[dict[str, Any]],
    advisory_findings: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Split old-style required_fixes into repairable, user-input, and advisory sets."""
    repairable: list[dict[str, Any]] = []
    user_input = list(needs_user_input)
    advisory = list(advisory_findings)
    for fix in required_fixes:
        if _is_user_input_fix(fix):
            user_input.append(fix)
        elif _is_advisory_output_format_fix(fix):
            advisory.append(_fix_to_advisory(fix))
        else:
            repairable.append(fix)
    return {
        "required_fixes": repairable,
        "needs_user_input": user_input,
        "advisory_findings": advisory,
    }


def _normalize_routing_recommendation(
    value: Any,
    *,
    status: str,
    required_fixes: list[dict[str, Any]],
    needs_user_input: list[dict[str, Any]],
) -> str:
    recommendation = str(value or "").strip().lower()
    if recommendation in {"accept", "repair_code", "request_user_input", "fail"}:
        return recommendation
    if status == "pass":
        return "accept"
    if status == "needs_user_input":
        return "request_user_input"
    if required_fixes:
        return "repair_code"
    if needs_user_input:
        return "request_user_input"
    return "fail"


def _is_user_input_fix(fix: dict[str, Any]) -> bool:
    text = _fix_text(fix)
    if any(
        phrase in text
        for phrase in (
            "user confirmation",
            "obtain user",
            "get user",
            "ask user",
            "human confirmation",
            "confirmed_by_user",
            "requires_confirmation",
            "unconfirmed",
            "user approval",
        )
    ):
        return True
    if "g4modelir" in text and any(
        phrase in text
        for phrase in (
            "update",
            "clarify",
            "change",
            "modify",
            "metadata",
            "add",
            "remove",
        )
    ):
        return True
    if "contradiction" in text and any(
        phrase in text for phrase in ("either", "which material", "material is intended")
    ):
        return True
    return False


def _is_advisory_output_format_fix(fix: dict[str, Any]) -> bool:
    text = _fix_text(fix)
    if "event_table.csv" not in text and "output" not in text:
        return False
    if not any(
        phrase in text
        for phrase in (
            "dose_gy",
            "eventid",
            "event_id",
            "field name",
            "column name",
            "extra column",
            "not specified",
            "additional column",
        )
    ):
        return False
    return not any(
        phrase in text
        for phrase in (
            "missing",
            "empty",
            "fake",
            "fallback",
            "placeholder",
            "fixed zero",
            "identical value",
            "row count",
            "expected events",
            "does not match",
        )
    )


def _fix_to_advisory(fix: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": str(fix.get("severity") or "low"),
        "target": str(fix.get("target") or "physics_review"),
        "message": str(fix.get("message") or ""),
    }


def _fix_text(fix: dict[str, Any]) -> str:
    return (
        f"{fix.get('target', '')}\n{fix.get('message', '')}"
    ).strip().lower()


def _model_info(result: Any) -> dict[str, Any]:
    return {
        "model_name": result.model_name,
        "tier": str(result.tier),
        "latency_ms": result.latency_ms,
        "error": result.error,
    }


def _score(value: Any) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(100, parsed))


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _g4_model_ir_for_review(g4_model_ir: Any) -> dict[str, Any]:
    if not isinstance(g4_model_ir, dict):
        return {}
    return {
        key: deepcopy(g4_model_ir.get(key))
        for key in (
            "schema_version",
            "model_ir_id",
            "job_id",
            "modeling_mode",
            "target_system",
            "simplification_policy",
            "global_units",
            "coordinate_system",
            "materials",
            "components",
            "sources",
            "physics",
            "sensitive_detectors",
            "interfaces",
            "scoring",
            "human_confirmation",
            "assumptions_confirmed",
            "confirmed_fields",
            "unconfirmed_fields",
        )
        if key in g4_model_ir
    }


def _global_integration_report_for_review(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    attempts = [
        _runtime_attempt_for_review(attempt)
        for attempt in report.get("runtime_gate_attempts", [])
        if isinstance(attempt, dict)
    ]
    return {
        key: deepcopy(report.get(key))
        for key in ("status", "report_path", "project_dir", "output_dir")
        if key in report
    } | {
        "runtime_gate_attempts": attempts,
        "runtime_gate_attempt_count": len(attempts),
        "repair_summary": _repair_summary_for_review(report),
    }


def _runtime_attempt_for_review(attempt: dict[str, Any]) -> dict[str, Any]:
    output_quality = attempt.get("output_quality", {})
    if not isinstance(output_quality, dict):
        output_quality = {}
    metrics = output_quality.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    smoke = attempt.get("smoke_result") or attempt.get("smoke_simulation_result") or {}
    if not isinstance(smoke, dict):
        smoke = {}
    errors = attempt.get("errors", [])
    if not isinstance(errors, list):
        errors = []
    return {
        "attempt": attempt.get("attempt"),
        "status": attempt.get("status"),
        "expected_events": attempt.get("expected_events") or metrics.get("expected_events"),
        "missing_outputs": _bounded_scalar_list(attempt.get("missing_outputs", []), 12),
        "error_count": len(errors),
        "errors_sample": _bounded_scalar_list(errors, 6),
        "output_quality": {
            "status": output_quality.get("status"),
            "error_count": len(output_quality.get("errors", []) or []),
            "errors_sample": _bounded_scalar_list(output_quality.get("errors", []), 6),
            "metrics": {
                key: metrics.get(key)
                for key in (
                    "events_requested",
                    "expected_events",
                    "event_table_rows",
                    "event_table_nonzero_rows",
                    "edep_3d_nonzero_rows",
                    "dose_3d_nonzero_rows",
                    "geometry_component_count",
                    "particle_track_count",
                    "energy_deposit_count",
                )
                if key in metrics
            },
        },
        "smoke": {
            "success": smoke.get("success"),
            "process_success": smoke.get("process_success"),
            "events_requested": smoke.get("events_requested"),
        },
    }


def _repair_summary_for_review(report: dict[str, Any]) -> dict[str, Any]:
    repairs = report.get("repair_attempts") or report.get("agentic_repair_attempts") or []
    if not isinstance(repairs, list):
        repairs = []
    return {
        "repair_attempt_count": len(repairs),
        "repairs_sample": [
            {
                "attempt": repair.get("attempt"),
                "status": repair.get("status"),
                "errors_sample": _bounded_scalar_list(repair.get("errors", []), 4),
            }
            for repair in repairs[:4]
            if isinstance(repair, dict)
        ],
    }


def _bounded_scalar_list(value: Any, limit: int) -> list[Any]:
    if not isinstance(value, list):
        return []
    result: list[Any] = []
    for item in value[:limit]:
        if isinstance(item, (str, int, float, bool)) or item is None:
            result.append(item)
        elif isinstance(item, dict):
            result.append(
                {
                    str(key): item.get(key)
                    for key in ("path", "target", "message", "status", "phase")
                    if key in item
                }
            )
        else:
            result.append(str(item))
    return result


def _project_files_for_review(
    proposed_patch: dict[str, Any],
    *,
    max_total_chars: int,
    max_chars_per_file: int,
) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    used_chars = 0
    changed_files = [
        item
        for item in proposed_patch.get("changed_files", [])
        if isinstance(item, dict)
    ]
    changed_files.sort(key=_project_file_review_priority)
    for item in changed_files:
        path = str(item.get("path", ""))
        content = str(item.get("new_content", ""))
        if not path or not content:
            continue
        remaining = max_total_chars - used_chars
        if remaining <= 0:
            break
        excerpt = _code_excerpt_for_review(
            path,
            content,
            max_chars=min(max_chars_per_file, remaining),
        )
        used_chars += len(excerpt)
        files.append(
            {
                "path": path,
                "module_name": str(item.get("module_name", "")),
                "generated_by": str(item.get("generated_by", "")),
                "content_chars": str(len(content)),
                "content_excerpt": excerpt,
                "excerpt_strategy": (
                    "line-numbered source excerpt containing physics, source, "
                    "geometry, scoring, output, and visualization-relevant code"
                ),
            }
        )
    return files


def _project_file_review_priority(item: dict[str, Any]) -> tuple[int, str]:
    path = str(item.get("path", ""))
    text = f"{path}\n{item.get('new_content', '')}"
    priority = 100
    important_patterns = (
        "src/PrimaryGeneratorAction.cc",
        "src/OutputManager.cc",
        "src/DetectorConstruction.cc",
        "src/PhysicsListFactoryWrapper.cc",
        "src/ScoringManager.cc",
        "src/SensitiveDetector.cc",
        "src/SteppingAction.cc",
        "src/EventAction.cc",
        "src/RunAction.cc",
        "macros/physics_list.mac",
        "macros/run.mac",
        "main.cc",
        "include/PrimaryGeneratorAction.hh",
        "include/OutputManager.hh",
        "include/DetectorConstruction.hh",
        "include/PhysicsListFactoryWrapper.hh",
        "include/ScoringManager.hh",
        "include/SensitiveDetector.hh",
    )
    for index, pattern in enumerate(important_patterns):
        if path == pattern:
            priority = min(priority, index)
    behavior_keywords = (
        "SetParticleEnergy",
        "GeneratePrimaries",
        "WriteEnergyDepositsJson",
        "WriteParticleTracksJson",
        "WriteGeometryViewJson",
        "G4PVPlacement",
        "FindOrBuildMaterial",
        "RegisterRegionScoring",
        "ProcessHits",
        "UserSteppingAction",
    )
    is_behavior_file = (
        path.startswith("src/")
        or path.startswith("macros/")
        or path == "main.cc"
        or path == "CMakeLists.txt"
    )
    if is_behavior_file and any(keyword in text for keyword in behavior_keywords):
        priority = max(0, priority - 5)
    if "geometry_view" in text or "particle_tracks" in text or "energy_deposits" in text:
        priority = min(priority, 8)
    return (priority, path)


def _code_excerpt_for_review(path: str, content: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    lines = content.splitlines()
    windows: list[tuple[int, int, int]] = []
    priority_keywords = _review_keywords_for_path(path)
    for index, line in enumerate(lines):
        lower_line = line.lower()
        for priority, keyword in priority_keywords:
            if keyword in lower_line:
                start = max(0, index - 2)
                end = min(len(lines), index + 4)
                windows.append((priority, start, end))
                break

    if not windows:
        windows = [(50, 0, min(len(lines), 40))]
    else:
        windows.insert(0, (40, 0, min(len(lines), 12)))
        windows.sort()

    chunks: list[str] = []
    emitted: set[int] = set()
    previous = -2
    used_chars = 0
    for _priority, start, end in windows:
        window_lines = [index for index in range(start, end) if index not in emitted]
        if not window_lines:
            continue
        candidate_lines: list[str] = []
        if previous != -2 and window_lines[0] > previous + 1:
            candidate_lines.append("...")
        candidate_lines.extend(f"{index + 1}: {lines[index]}" for index in window_lines)
        candidate = "\n".join(candidate_lines)
        separator = "\n" if chunks else ""
        if used_chars + len(separator) + len(candidate) > max_chars:
            continue
        if separator:
            chunks.append(separator.rstrip("\n"))
        chunks.extend(candidate_lines)
        used_chars += len(separator) + len(candidate)
        emitted.update(window_lines)
        previous = window_lines[-1]

    excerpt = "\n".join(chunks)
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 32] + "\n[truncated source excerpt]"
    if len(content) > len(excerpt):
        excerpt += (
            f"\n[excerpted {len(excerpt)} of {len(content)} chars from {path}]"
        )
    return excerpt


def _review_keywords_for_path(path: str) -> list[tuple[int, str]]:
    output_first = path.endswith("OutputManager.cc")
    priority_map: dict[str, int] = {}
    for keyword in REVIEW_SOURCE_KEYWORDS:
        priority_map[keyword.lower()] = 20
    for keyword in (
        "SetParticleEnergy",
        "SetParticlePosition",
        "SetParticleMomentumDirection",
        "FindParticle",
        "GeneratePrimaries",
        "FTFP_BERT",
        "G4PVPlacement",
        "FindOrBuildMaterial",
        "ProcessHits",
        "UserSteppingAction",
    ):
        priority_map[keyword.lower()] = 5
    for keyword in (
        "WriteEventTable",
        "WriteEdep3D",
        "WriteDose3D",
        "WriteGeometryViewJson",
        "WriteParticleTracksJson",
        "WriteEnergyDepositsJson",
        "AddTrackPoint",
        "AddEnergyDepositPoint",
        "EventID",
    ):
        priority_map[keyword.lower()] = 3 if output_first else 8
    return sorted(
        ((priority, keyword) for keyword, priority in priority_map.items()),
        key=lambda item: (item[0], item[1]),
    )


def _runtime_verification_summary(report: Any) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    attempts = [
        attempt
        for attempt in report.get("runtime_gate_attempts", [])
        if isinstance(attempt, dict)
    ]
    latest = _latest_runtime_attempt(attempts)
    prior_failures = [
        attempt
        for attempt in attempts
        if attempt is not latest and str(attempt.get("status", "")).lower() != "pass"
    ]
    if not latest:
        return {
            "global_integration_status": report.get("status"),
            "latest_runtime_gate_passed": False,
            "prior_failed_attempt_count": len(prior_failures),
        }

    output_quality = latest.get("output_quality", {})
    if not isinstance(output_quality, dict):
        output_quality = {}
    metrics = output_quality.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    smoke = latest.get("smoke_result") or latest.get("smoke_simulation_result") or {}
    if not isinstance(smoke, dict):
        smoke = {}
    return {
        "global_integration_status": report.get("status"),
        "latest_attempt": latest.get("attempt"),
        "latest_runtime_gate_status": latest.get("status"),
        "latest_runtime_gate_passed": latest.get("status") == "pass",
        "prior_failed_attempt_count": len(prior_failures),
        "expected_events": latest.get("expected_events") or metrics.get("expected_events"),
        "events_requested": metrics.get("events_requested"),
        "missing_outputs": latest.get("missing_outputs", []),
        "error_count": len(latest.get("errors", []) or []),
        "output_quality_status": output_quality.get("status"),
        "output_quality_errors": output_quality.get("errors", []),
        "event_table_rows": metrics.get("event_table_rows"),
        "event_table_nonzero_rows": metrics.get("event_table_nonzero_rows"),
        "edep_3d_nonzero_rows": metrics.get("edep_3d_nonzero_rows"),
        "dose_3d_nonzero_rows": metrics.get("dose_3d_nonzero_rows"),
        "smoke_success": smoke.get("success"),
        "smoke_process_success": smoke.get("process_success"),
    }


def _latest_runtime_attempt(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    if not attempts:
        return {}

    def key(attempt: dict[str, Any]) -> tuple[int, int]:
        value = attempt.get("attempt")
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = -1
        return (parsed, attempts.index(attempt))

    return max(attempts, key=key)


def _compact_module_contracts(module_contracts: Any) -> dict[str, Any]:
    if not isinstance(module_contracts, dict):
        return {}
    compact: dict[str, Any] = {}
    for module_name, contract in module_contracts.items():
        if not isinstance(contract, dict):
            continue
        compact[str(module_name)] = {
            key: contract.get(key)
            for key in ("responsibilities", "output_files", "required_symbols", "dependencies")
            if contract.get(key) is not None
        }
    return compact


def _compact_module_contexts(module_contexts: Any) -> dict[str, Any]:
    if not isinstance(module_contexts, dict):
        return {}
    compact: dict[str, Any] = {}
    for module_name, context in module_contexts.items():
        if not isinstance(context, dict):
            continue
        compact[str(module_name)] = {
            "module_name": context.get("module_name"),
            "g4_model_ir_subset": _module_ir_subset_for_review(
                context.get("g4_model_ir_subset", {})
            ),
            "geant4_api_rules": _bounded_scalar_list(
                context.get("geant4_api_rules", []),
                8,
            ),
            "example_lookup_used": bool(context.get("geant4_example_lookup_results")),
        }
    return compact


def _module_ir_subset_for_review(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    unit_contract = value.get("unit_contract", {})
    if not isinstance(unit_contract, dict):
        unit_contract = {}
    return {
        "model_ir_id": value.get("model_ir_id"),
        "modeling_mode": value.get("modeling_mode"),
        "target_system": value.get("target_system"),
        "global_units": deepcopy(value.get("global_units")),
        "unit_contract": {
            key: unit_contract.get(key)
            for key in (
                "dimension_semantics",
                "box_dimension_rule",
                "placement_rule",
            )
            if key in unit_contract
        },
        "component_ids": [
            item.get("component_id")
            for item in value.get("components", [])
            if isinstance(item, dict) and item.get("component_id")
        ],
        "material_ids": [
            item.get("material_id")
            for item in value.get("materials", [])
            if isinstance(item, dict) and item.get("material_id")
        ],
        "source_summaries": [
            {
                key: item.get(key)
                for key in ("source_id", "particle_type", "energy", "beam", "events")
                if key in item
            }
            for item in value.get("sources", [])
            if isinstance(item, dict)
        ],
        "physics": deepcopy(value.get("physics")),
        "scoring_summaries": [
            {
                key: item.get(key)
                for key in ("scoring_id", "scoring_type", "quantities")
                if key in item
            }
            for item in value.get("scoring", [])
            if isinstance(item, dict)
        ],
        "sensitive_detector_ids": [
            item.get("sd_id") or item.get("name")
            for item in value.get("sensitive_detectors", [])
            if isinstance(item, dict) and (item.get("sd_id") or item.get("name"))
        ],
        "interface_ids": [
            item.get("interface_id")
            for item in value.get("interfaces", [])
            if isinstance(item, dict) and item.get("interface_id")
        ],
        "human_confirmation_context": deepcopy(
            value.get("human_confirmation_context")
        ),
    }


def _trim_json_value(value: Any, *, max_chars: int) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    if len(text) <= max_chars:
        return value
    return {"summary": text[: max_chars - 32] + "\n[truncated for review]"}


def _review_prompt_json(context: dict[str, Any], *, max_chars: int) -> str:
    prompt = json.dumps(context, indent=2, ensure_ascii=False)
    if len(prompt) <= max_chars:
        return prompt

    compact = deepcopy(context)
    compact["module_context_summaries"] = {
        module_name: {
            "module_name": module_context.get("module_name"),
            "example_lookup_used": module_context.get("example_lookup_used"),
            "g4_model_ir_subset": _compact_review_ir_lists(
                module_context.get("g4_model_ir_subset", {}),
                max_items=8,
            ),
            "geant4_api_rules": module_context.get("geant4_api_rules", [])[:4],
        }
        for module_name, module_context in compact.get(
            "module_context_summaries", {}
        ).items()
        if isinstance(module_context, dict)
    }
    compact["g4_model_ir"] = _compact_review_ir_lists(
        compact.get("g4_model_ir", {}),
        max_items=12,
    )
    compact["project_files"] = _shrink_project_file_excerpts(
        compact.get("project_files", []),
        max_chars_per_file=1_800,
    )
    prompt = json.dumps(compact, indent=2, ensure_ascii=False)
    if len(prompt) <= max_chars:
        return prompt

    compact["project_files"] = _shrink_project_file_excerpts(
        compact.get("project_files", []),
        max_chars_per_file=900,
    )
    prompt = json.dumps(compact, indent=2, ensure_ascii=False)
    if len(prompt) <= max_chars:
        return prompt

    compact["module_context_summaries"] = {
        module_name: {
            "module_name": module_context.get("module_name"),
            "example_lookup_used": module_context.get("example_lookup_used"),
            "g4_model_ir_subset": {
                key: module_context.get("g4_model_ir_subset", {}).get(key)
                for key in (
                    "model_ir_id",
                    "modeling_mode",
                    "target_system",
                    "global_units",
                    "component_ids",
                    "material_ids",
                    "source_summaries",
                    "scoring_summaries",
                    "sensitive_detector_ids",
                    "interface_ids",
                    "human_confirmation_context",
                )
                if isinstance(module_context.get("g4_model_ir_subset", {}), dict)
                and key in module_context.get("g4_model_ir_subset", {})
            },
        }
        for module_name, module_context in compact.get(
            "module_context_summaries", {}
        ).items()
        if isinstance(module_context, dict)
    }
    prompt = json.dumps(compact, indent=2, ensure_ascii=False)
    if len(prompt) <= max_chars:
        return prompt

    compact["project_files"] = []
    compact["context_budget_note"] = (
        "Project file excerpts omitted because the bounded review prompt still "
        "exceeded the physics reviewer context budget after structured compaction."
    )
    return json.dumps(compact, indent=2, ensure_ascii=False)


def _compact_review_ir_lists(value: Any, *, max_items: int) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, list):
                result[key] = item[:max_items]
                if len(item) > max_items:
                    result[f"{key}_omitted_count"] = len(item) - max_items
            else:
                result[key] = _compact_review_ir_lists(item, max_items=max_items)
        return result
    if isinstance(value, list):
        result = value[:max_items]
        if len(value) > max_items:
            result = result + [{"omitted_count": len(value) - max_items}]
        return result
    return value


def _shrink_project_file_excerpts(
    files: Any,
    *,
    max_chars_per_file: int,
) -> list[dict[str, str]]:
    if not isinstance(files, list):
        return []
    result: list[dict[str, str]] = []
    for file in files:
        if not isinstance(file, dict):
            continue
        compact = dict(file)
        excerpt = str(compact.get("content_excerpt", ""))
        if len(excerpt) > max_chars_per_file:
            compact["content_excerpt"] = (
                excerpt[: max_chars_per_file - 32]
                + "\n[truncated source excerpt]"
            )
        result.append(compact)
    return result


def _persist_review(review: dict[str, Any], job_id: str) -> None:
    codegen_dir = get_job_dir(job_id) / STAGE_CODEGEN
    codegen_dir.mkdir(parents=True, exist_ok=True)
    (codegen_dir / "physics_quality_review.json").write_text(
        json.dumps(review, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
