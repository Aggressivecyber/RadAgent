"""Base class for module LLM gates — semantic checks via ModelGateway."""

from __future__ import annotations

import json
from typing import Any

from agent_core.g4_codegen.schemas import ModuleGateResult
from agent_core.models.gateway import _safe_parse_json, get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier

OVERALL_PASS_THRESHOLD = 0.85
DIMENSION_PASS_THRESHOLD = 0.75
REQUIRED_DIMENSIONS = {
    "contract_compliance",
    "geant4_correctness",
    "interface_consistency",
    "hallucination_risk",
    "compile_risk",
}

MODULE_LLM_GATE_SYSTEM_PROMPT = """你是 RadAgent 的 Geant4 模块审查 Agent。
你只审查当前模块，不审查整个工程。

请根据 ModuleContract、ModuleContext、G4ModelIR 子集、
生成文件内容、硬门禁结果，
判断当前模块是否可以进入集成阶段。

你必须检查：
1. 是否忠于 G4ModelIR；
2. 是否存在未批准简化；
3. 是否存在职责越界；
4. 是否存在与其他模块接口不清；
5. 是否存在明显 Geant4 API 错误；
6. 是否存在物理建模风险；
7. 是否需要 human confirmation；
8. 是否可以进入 integration。
9. 只根据 ModuleContract 中声明的 dependencies 和 responsibilities 要求跨模块接口；
   不得要求当前模块连接未声明的依赖模块。
10. 如果某个跨模块连接应由 integration、action_initialization 或 output_manager 负责，
    不得把该要求作为当前模块失败原因。

输出要求：
1. 只输出一个 JSON 对象；
2. 不得输出 Markdown、代码围栏、解释文字、前后缀文本；
3. JSON 字段名必须使用下面的固定 schema；
4. status 只能是 "pass" 或 "fail"；
5. 分数必须是 0 到 1 之间的数字。

返回严格 JSON：
{
  "status": "pass | fail",
  "module_name": "...",
  "overall_score": 0.0,
  "dimensions": {
    "contract_compliance": 0.0,
    "geant4_correctness": 0.0,
    "interface_consistency": 0.0,
    "hallucination_risk": 0.0,
    "compile_risk": 0.0
  },
  "semantic_checks": [
    {"check": "...", "status": "pass | fail", "message": "...", "evidence": "..."}
  ],
  "risks": [],
  "blocking_issues": [],
  "required_fixes": [],
  "requires_human_confirmation": false,
  "reviewer_notes": "..."
}

通过条件：
- overall_score 必须 >= 0.85；
- 每个 dimensions 分数必须 >= 0.75；
- blocking_issues 必须为空；
- 若发现幻觉、伪实现、未按 ModuleContract 输出、明显 Geant4 API 错误，必须 fail。
"""


async def run_llm_gate(
    module_name: str,
    module_context: dict[str, Any],
    generated_files_content: list[dict[str, Any]],
    hard_gate_result: dict[str, Any],
) -> ModuleGateResult:
    """Run LLM gate for a module.

    Only runs if hard gate passed.
    Uses ModelGateway with GATE_EXPLANATION task and MAX tier.
    """
    # Check hard gate status
    if hard_gate_result.get("status") == "fail":
        return ModuleGateResult(
            module_name=module_name,
            gate_type="llm",
            status="skipped",
            checks=[],
            errors=["Hard gate failed — LLM gate skipped"],
        )

    gateway = get_model_gateway()
    job_id = (
        module_context.get("job_id")
        or module_context.get("g4_model_ir_subset", {}).get("job_id")
        or ""
    )

    user_prompt = f"""模块名称：{module_name}

模块专用审查事实和约束：
{json.dumps(_module_review_requirements(module_name), indent=2, ensure_ascii=False)}

模块上下文：
{json.dumps(module_context, indent=2, ensure_ascii=False)[:12000]}

生成文件内容摘要：
{json.dumps(generated_files_content, indent=2, ensure_ascii=False)[:12000]}

硬门禁结果：
{json.dumps(hard_gate_result, indent=2, ensure_ascii=False)[:2000]}

请判断当前模块是否可以进入集成阶段。返回 JSON。"""

    data: dict[str, Any] | None = None
    parse_errors: list[str] = []
    for attempt in range(1, 3):
        retry_suffix = "" if attempt == 1 else "\n\n上一次返回不是有效 JSON。请只返回 JSON 对象。"
        result = await gateway.call(
            task=ModelTask.GATE_EXPLANATION,
            tier=ModelTier.MAX,
            system_prompt=MODULE_LLM_GATE_SYSTEM_PROMPT,
            user_prompt=user_prompt + retry_suffix,
            response_format="json",
            max_tokens=4096,
            metadata={"module_name": module_name, "job_id": job_id, "attempt": attempt},
        )

        if result.error:
            return ModuleGateResult(
                module_name=module_name,
                gate_type="llm",
                status="fail",
                checks=[],
                errors=[f"LLM gate call failed: {result.error}"],
            )

        try:
            data = result.parsed_json or _safe_parse_json(result.content) or json.loads(
                result.content.strip()
            )
            break
        except (json.JSONDecodeError, TypeError) as exc:
            parse_errors.append(f"attempt {attempt}: {exc}")

    if data is None:
        return ModuleGateResult(
            module_name=module_name,
            gate_type="llm",
            status="fail",
            checks=[],
            errors=["Invalid JSON from LLM gate after retry", *parse_errors],
        )

    scorecard = _normalize_scorecard(data)
    score_errors = _scorecard_errors(scorecard)
    required_fixes = _normalize_messages(data.get("required_fixes", []))
    blocking_issues = _normalize_messages(data.get("blocking_issues", []))
    normalized_status = _normalize_gate_status(data.get("status", "fail"))
    if normalized_status == "pass" and (score_errors or blocking_issues):
        normalized_status = "fail"

    return ModuleGateResult(
        module_name=module_name,
        gate_type="llm",
        status=normalized_status,
        checks=_normalize_checks(data.get("semantic_checks", data.get("checks", []))),
        errors=[*score_errors, *blocking_issues, *required_fixes],
        warnings=_normalize_messages(data.get("risks", [])),
        reviewer_notes=data.get("reviewer_notes"),
        scorecard=scorecard,
    )


def _normalize_gate_status(value: Any) -> str:
    status = str(value or "fail").lower()
    if status in {"pass", "passed", "ok"}:
        return "pass"
    if status in {"skipped", "skip"}:
        return "skipped"
    return "fail"


def _normalize_checks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        value = [value] if value else []
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(value, start=1):
        if isinstance(item, dict):
            check = dict(item)
            check.setdefault("check", f"semantic_check_{idx}")
            check.setdefault("status", "pass")
            check.setdefault("message", "")
            normalized.append(check)
        else:
            normalized.append(
                {
                    "check": f"semantic_check_{idx}",
                    "status": "pass",
                    "message": str(item),
                }
            )
    return normalized


def _normalize_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [value] if value else []
    messages: list[str] = []
    for item in value:
        if isinstance(item, dict):
            messages.append(json.dumps(item, ensure_ascii=False))
        else:
            messages.append(str(item))
    return messages


def _normalize_scorecard(data: dict[str, Any]) -> dict[str, Any]:
    dimensions_raw = data.get("dimensions", {})
    if not isinstance(dimensions_raw, dict):
        dimensions_raw = {}

    dimensions: dict[str, float] = {}
    for name in REQUIRED_DIMENSIONS:
        raw = dimensions_raw.get(name)
        if isinstance(raw, dict):
            raw = raw.get("score")
        dimensions[name] = _score_to_float(raw)

    return {
        "overall_score": _score_to_float(data.get("overall_score")),
        "dimensions": dimensions,
        "thresholds": {
            "overall_score": OVERALL_PASS_THRESHOLD,
            "dimension_score": DIMENSION_PASS_THRESHOLD,
        },
    }


def _score_to_float(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, score))


def _scorecard_errors(scorecard: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    overall = float(scorecard.get("overall_score", 0.0))
    if overall < OVERALL_PASS_THRESHOLD:
        errors.append(
            f"LLM gate overall_score {overall:.2f} below threshold "
            f"{OVERALL_PASS_THRESHOLD:.2f}"
        )
    dimensions = scorecard.get("dimensions", {})
    for name in sorted(REQUIRED_DIMENSIONS):
        score = float(dimensions.get(name, 0.0))
        if score < DIMENSION_PASS_THRESHOLD:
            errors.append(
                f"LLM gate dimension '{name}' score {score:.2f} below threshold "
                f"{DIMENSION_PASS_THRESHOLD:.2f}"
            )
    return errors


def _module_review_requirements(module_name: str) -> list[str]:
    """Facts the LLM gate must use when reviewing module-specific APIs."""
    if module_name == "scoring":
        return [
            (
                "For this project's installed Geant4, "
                "G4VScoringMesh.hh defines MeshScoreMap as "
                "std::map<G4String, G4THitsMap<G4StatDouble>*>."
            ),
            (
                "For this project's installed Geant4, "
                "G4VScoringMesh::GetScoreMap() exists and returns MeshScoreMap."
            ),
            (
                "Do not fail scoring code merely for using G4VScoringMesh::GetScoreMap(); "
                "that API is the required command-based scoring mesh read path here."
            ),
            (
                "Do fail scoring code that uses mesh->GetScorer(), GetHitsMap(), "
                "G4VScorer, or dynamic_cast to G4THitsMap."
            ),
            (
                "A correct scoring read assigns scoreMap.find(...)->second directly to "
                "G4THitsMap<G4StatDouble>* and extracts values with GetObject(copyNo) "
                "or GetMap()->find(copyNo), then G4StatDouble::sum_wx()."
            ),
            (
                "Scoring code must obtain the manager singleton with "
                "G4ScoringManager::GetScoringManager(); do not allocate it with new."
            ),
        ]
    if module_name == "sensitive_detector":
        return [
            (
                "G4VSensitiveDetector.hh documents that concrete sensitive detectors "
                "must set hits collection names in the protected collectionName vector."
            ),
            (
                "Do not fail code merely because it calls collectionName.push_back(...); "
                "this is the required way to register the hits collection name here."
            ),
            (
                "SensitiveDetector.cc must include G4THitsCollection.hh when it directly "
                "uses G4THitsCollection<::Hit>."
            ),
            (
                "SensitiveDetector must add hits to G4THitsCollection with insert(hit); "
                "do not accept fHitsCollection->push_back(hit)."
            ),
            (
                "#include <iomanip> is a valid C++ standard header and is required when "
                "Hit.cc uses std::setw, std::setprecision, or std::fixed."
            ),
        ]
    if module_name == "output_manager":
        return [
            (
                "This project's OutputManager contract explicitly requires the stable "
                "action-facing methods BeginRun(const G4Run*), EndRun(const G4Run*), "
                "BeginEvent(const G4Event*), EndEvent(const G4Event*), "
                "RecordStep(const G4Step*), and WriteEvent(const G4Event*)."
            ),
            (
                "Do not fail OutputManager merely because it declares or defines "
                "RecordStep(const G4Step*); that method is part of the required "
                "OutputManager interface for action modules."
            ),
            (
                "Do fail OutputManager if RecordStep constructs geometry, queries "
                "ScoringManager directly, or changes source/physics state. It may only "
                "record or aggregate output data."
            ),
            (
                "OutputManager must provide a one-argument WriteEvent(const G4Event*) "
                "adapter even if it also provides overloads with scoring values."
            ),
            (
                "Do fail OutputManager when dose_Gy is always hard-coded as 0.0. A passing "
                "implementation must expose an explicit dose input path such as "
                "SetEventDoseGy(G4double) or WriteEvent(const G4Event*, G4double, G4double), "
                "while keeping the one-argument WriteEvent adapter."
            ),
        ]
    return []
