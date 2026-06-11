from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent_core.models.gateway import get_model_gateway
from agent_core.models.schemas import ModelTask, ModelTier

BRIEFING_SYSTEM_PROMPT = """\
你是 RadAgent 的仿真简报 Copilot，负责在正式启动 pipeline 前与用户打磨方案。

你的任务不是闲聊，也不能直接声称已经启动仿真。你必须用最强规划能力，把用户需求整理成
足够下游 workflow 使用的完整仿真需求包，并在需要时提出高质量问题。

硬性规则：
1. 所有自然语言仿真请求都必须经过本简报阶段。
2. 你必须尽可能全面地识别缺失信息、风险、假设和下游代码生成需求。
3. 如果信息不足，status 输出 needs_input，只在 next_question 给出一个最高优先级的
   引导式问题；其他问题放入 hidden_questions。
4. 如果信息足够，status 输出 ready_for_approval，并给出需要人类批准的启动请求。
5. 即使 ready_for_approval，也不能跳过人类批准。
6. ready_for_approval 时必须输出 proposed_command，且只能是 pending 的 start_job 写操作。
7. 不要输出 Markdown；只输出符合 schema 的 JSON。
8. final_query 必须是可直接交给 RadAgent pipeline 的完整自然语言任务说明。
9. needs_input 阶段 questions 可以保留兼容字段，但主问题必须由 next_question 承载，
   且一次只问一个问题。

必须覆盖的计划字段：
- objective: 物理目标、问题、成功标准
- simulation_scope: Geant4、TCAD、ngspice 或混合范围
- space_radiation: 如果用户提到空间轨道、卫星轨道、Van Allen、AP8/AE8 或轨道辐照，
  必须识别为 trapped-radiation environment briefing。优先使用本地 AP8/AE8 数据扩展，
  追问 particle(proton/electron)、solar_period(min/max)、flux_mode(integral/differential)、
  TLE 或 geodetic orbit samples 或 L-shell/B/B0、屏蔽/目标、scoring 和 events。
  altitude/inclination 可以记录，但不能单独当作 AP8/AE8 源项充分条件；如果没有 TLE、
  geodetic samples 或 L-shell/B/B0，status 必须是 needs_input。AP8/AE8 是静态 trapped
  belt 经验模型，不是 dynamic space-weather、solar proton event 或 GCR 模型。运行环境
  使用 aep8/astropy/skyfield/sgp4 计算真实 AP8/AE8 通量。
- geometry: 体、尺寸、层级、坐标系、边界和单位
- materials: 材料名、密度/组分、掺杂或特殊属性
- source: 粒子种类、能量、方向、位置、束斑、事件数
- physics: physics list、cut、range、二次粒子策略
- scoring: scoring 区域、记录量、binning、输出格式
- run_plan: 快速验证规模、正式运行规模、随机种子策略
- codegen_constraints: 模块边界、命名、文件组织、必须保留的约束
- assumptions: 明确假设，尤其是会影响结果可信度的假设
- risks: 风险和影响
"""

APPROVED_PLAN_SUMMARY_PROMPT = """\
You create compact task labels for an approved RadAgent simulation plan.

Return JSON only with exactly these keys:
{
  "zh": "中文任务摘要，50字以内",
  "en": "English task summary, 50 characters or fewer"
}

Rules:
1. Summarize the approved simulation task, not the approval process.
2. Mention the main object/system and primary simulation goal.
3. Do not include job IDs, dates, commands, Markdown, or explanations.
4. Keep both values short enough for a terminal side panel.
"""

BRIEFING_MEMORY_COMPACTION_PROMPT = """\
You compact historical RadAgent simulation briefing memory.

Return JSON only with these keys:
{
  "stable_facts": [],
  "answered_fields": {},
  "open_questions": [],
  "rejected_options": [],
  "latest_user_intent": "",
  "risk_notes": []
}

Rules:
1. Compact only the historical briefing memory supplied by the user prompt.
2. Preserve decisions, constraints, assumptions, rejected options, and unresolved questions.
3. Do not summarize the current latest user message as if it were already resolved.
4. Do not include Markdown or explanatory prose outside JSON.
"""

BRIEFING_JSON_REPAIR_PROMPT = """\
You repair a RadAgent simulation briefing response into valid JSON.

Return JSON only. Do not include Markdown, commentary, or code fences.

Rules:
1. Preserve the user's simulation intent and any useful facts from the failed response.
2. If the failed response lacks enough information for approval, return status needs_input.
3. If status is needs_input, include exactly one next_question and put other questions in
   hidden_questions.
4. If status is ready_for_approval, include final_query, proposed_command, and
   approval_request.requires_human_approval=true.
5. Never claim the simulation has started.
"""

_HISTORY_COMPACTION_THRESHOLD = 0.75
_RECENT_HISTORY_TURNS = 4
_DEFAULT_CONTEXT_WINDOW_TOKENS = 128_000


class BriefingApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    requires_human_approval: bool = True
    summary: str
    risks: list[str] = Field(default_factory=list)

    @field_validator("requires_human_approval")
    @classmethod
    def _must_require_human_approval(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("approval_request.requires_human_approval must be true")
        return value


class BriefingProposedCommand(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Literal["start_job"]
    args: dict[str, Any] = Field(default_factory=dict)
    risk: Literal["write"] = "write"
    status: Literal["pending"] = "pending"
    summary: str = ""


class BriefingQuestion(BaseModel):
    model_config = ConfigDict(extra="allow")

    field: str = ""
    question: str
    choices: list[str] = Field(default_factory=list)
    why: str = ""


class SimulationBriefingResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["needs_input", "ready_for_approval"]
    understanding: str
    next_question: BriefingQuestion | None = None
    hidden_questions: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    draft_plan: dict[str, Any] = Field(default_factory=dict)
    missing_critical_fields: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    final_query: str = ""
    compacted_briefing_memory: dict[str, Any] = Field(default_factory=dict)
    context_window_stats: dict[str, Any] = Field(default_factory=dict)
    proposed_command: BriefingProposedCommand | None = None
    approval_request: BriefingApprovalRequest | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_approval_request(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        approval = data.get("approval_request")
        if isinstance(approval, Mapping):
            normalized = dict(approval)
            normalized["requires_human_approval"] = True
            data = dict(data)
            data["approval_request"] = normalized
            return data
        if isinstance(approval, bool):
            data = dict(data)
            data["approval_request"] = {
                "requires_human_approval": True,
                "summary": str(
                    data.get("final_query") or data.get("understanding") or "Start simulation."
                ),
                "risks": _list_value(data.get("risks")),
            }
        return data

    @field_validator("final_query")
    @classmethod
    def _final_query_required_for_approval(cls, value: str, info: Any) -> str:
        status = info.data.get("status")
        if status == "ready_for_approval" and not value.strip():
            raise ValueError("final_query is required when ready_for_approval")
        return value

    @field_validator("proposed_command")
    @classmethod
    def _command_required_for_approval(
        cls,
        value: BriefingProposedCommand | None,
        info: Any,
    ) -> BriefingProposedCommand | None:
        status = info.data.get("status")
        if status == "ready_for_approval" and value is None:
            raise ValueError("proposed_command is required when ready_for_approval")
        return value

    @property
    def ready_for_approval(self) -> bool:
        return self.status == "ready_for_approval"

    def summary_text(self) -> str:
        if self.approval_request is not None:
            return self.approval_request.summary
        if self.next_question is not None:
            lines = [self.next_question.question]
            lines.extend(
                f"{index}. {choice}"
                for index, choice in enumerate(self.next_question.choices, start=1)
            )
            return "\n".join(lines)
        if self.questions:
            return "需要补充信息: " + self.questions[0]
        return self.understanding


class SimulationBriefingPlanner:
    def __init__(self, *, gateway_factory: Callable[[], Any] = get_model_gateway) -> None:
        self._gateway_factory = gateway_factory

    async def brief(
        self,
        *,
        user_message: str,
        conversation: Sequence[Mapping[str, str]],
        workflow_context: Mapping[str, Any],
    ) -> SimulationBriefingResult:
        gateway = self._gateway_factory()
        prompt_state = await _prepare_briefing_prompt_state(
            gateway=gateway,
            user_message=user_message,
            conversation=conversation,
            workflow_context=workflow_context,
        )
        result = await gateway.call(
            task=ModelTask.SIMULATION_BRIEFING,
            tier=ModelTier.MAX,
            system_prompt=BRIEFING_SYSTEM_PROMPT,
            user_prompt=_build_briefing_user_prompt(
                user_message=user_message,
                conversation=prompt_state.conversation,
                workflow_context=workflow_context,
                compacted_briefing_memory=prompt_state.compacted_memory,
                context_window_stats=prompt_state.stats,
            ),
            response_format="json",
            temperature=0.0,
            max_tokens=8192,
            metadata={"module_name": "simulation_briefing"},
        )
        if result.error:
            raise RuntimeError(f"Simulation briefing failed: {result.error}")
        data = _briefing_json_from_result(result)
        if not data:
            repair = await _repair_briefing_json(
                gateway=gateway,
                user_message=user_message,
                workflow_context=workflow_context,
                failed_result=result,
            )
            data = _briefing_json_from_result(repair)
        if not data:
            data = _fallback_needs_input_briefing(user_message)
        briefing = SimulationBriefingResult.model_validate(data)
        briefing.compacted_briefing_memory = prompt_state.compacted_memory
        briefing.context_window_stats = prompt_state.stats
        if briefing.ready_for_approval and briefing.approval_request is None:
            raise ValueError("approval_request is required when ready_for_approval")
        if briefing.ready_for_approval and briefing.proposed_command is None:
            raise ValueError("proposed_command is required when ready_for_approval")
        return briefing


@dataclass(frozen=True)
class _BriefingPromptState:
    conversation: list[dict[str, str]]
    compacted_memory: dict[str, Any]
    stats: dict[str, Any]


async def _prepare_briefing_prompt_state(
    *,
    gateway: Any,
    user_message: str,
    conversation: Sequence[Mapping[str, str]],
    workflow_context: Mapping[str, Any],
) -> _BriefingPromptState:
    turns = [_turn_to_dict(turn) for turn in conversation]
    history, latest_turn = _split_latest_turn(turns, user_message)
    context_window_tokens = _context_window_tokens(gateway, ModelTier.MAX)
    history_tokens = _estimate_tokens(history)
    usage_ratio = history_tokens / context_window_tokens if context_window_tokens else 0.0
    older_history = history[:-_RECENT_HISTORY_TURNS]
    recent_history = history[-_RECENT_HISTORY_TURNS:]
    should_compact = bool(
        older_history and usage_ratio > _HISTORY_COMPACTION_THRESHOLD
    )
    stats = {
        "history_estimated_tokens": history_tokens,
        "context_window_tokens": context_window_tokens,
        "history_usage_ratio": round(usage_ratio, 4),
        "threshold": _HISTORY_COMPACTION_THRESHOLD,
        "compacted": should_compact,
        "state": "compacted" if should_compact else "normal",
        "cycle": 1 if should_compact else 0,
        "recent_history_turns": len(recent_history),
    }

    if not should_compact:
        return _BriefingPromptState(
            conversation=turns,
            compacted_memory={},
            stats=stats,
        )

    compacted_memory = await _compact_historical_briefing_memory(
        gateway=gateway,
        older_history=older_history,
        user_message=user_message,
        workflow_context=workflow_context,
    )
    compacted_conversation = list(recent_history)
    if latest_turn is not None:
        compacted_conversation.append(latest_turn)
    stats["compacted_history_turns"] = len(older_history)
    return _BriefingPromptState(
        conversation=compacted_conversation,
        compacted_memory=compacted_memory,
        stats=stats,
    )


async def _compact_historical_briefing_memory(
    *,
    gateway: Any,
    older_history: Sequence[Mapping[str, str]],
    user_message: str,
    workflow_context: Mapping[str, Any],
) -> dict[str, Any]:
    result = await gateway.call(
        task=ModelTask.CONTEXT_SUMMARY,
        tier=ModelTier.LITE,
        system_prompt=BRIEFING_MEMORY_COMPACTION_PROMPT,
        user_prompt=json.dumps(
            {
                "historical_briefing_memory": list(older_history),
                "latest_user_message": user_message,
                "workflow_context": dict(workflow_context),
                "output_schema": {
                    "stable_facts": [],
                    "answered_fields": {},
                    "open_questions": [],
                    "rejected_options": [],
                    "latest_user_intent": "",
                    "risk_notes": [],
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        response_format="json",
        temperature=0.0,
        max_tokens=2048,
        metadata={"module_name": "briefing_memory_compaction"},
    )
    if result.error:
        return _fallback_compacted_memory(older_history)
    data = result.parsed_json or _parse_json_object(result.content)
    if not data:
        return _fallback_compacted_memory(older_history)
    return {
        "stable_facts": _list_value(data.get("stable_facts")),
        "answered_fields": data.get("answered_fields", {})
        if isinstance(data.get("answered_fields"), dict)
        else {},
        "open_questions": _list_value(data.get("open_questions")),
        "rejected_options": _list_value(data.get("rejected_options")),
        "latest_user_intent": str(data.get("latest_user_intent", "")),
        "risk_notes": _list_value(data.get("risk_notes")),
    }


class ApprovedPlanSummarizer:
    def __init__(self, *, gateway_factory: Callable[[], Any] = get_model_gateway) -> None:
        self._gateway_factory = gateway_factory

    async def summarize(self, briefing_context: Mapping[str, Any]) -> dict[str, str]:
        gateway = self._gateway_factory()
        result = await gateway.call(
            task=ModelTask.CONTEXT_SUMMARY,
            tier=ModelTier.LITE,
            system_prompt=APPROVED_PLAN_SUMMARY_PROMPT,
            user_prompt=_build_approved_summary_prompt(briefing_context),
            response_format="json",
            temperature=0.0,
            max_tokens=256,
            metadata={"module_name": "approved_plan_summary"},
        )
        if result.error:
            raise RuntimeError(f"Approved plan summary failed: {result.error}")
        data = result.parsed_json or _parse_json_object(result.content)
        zh = _clip_summary(data.get("zh") or data.get("chinese"))
        en = _clip_summary(data.get("en") or data.get("english"))
        fallback = _fallback_summary_text(briefing_context)
        if not zh:
            zh = _clip_summary(fallback)
        if not en:
            en = _clip_summary(fallback)
        return {"zh": zh, "en": en}


def _build_briefing_user_prompt(
    *,
    user_message: str,
    conversation: Sequence[Mapping[str, str]],
    workflow_context: Mapping[str, Any],
    compacted_briefing_memory: Mapping[str, Any] | None = None,
    context_window_stats: Mapping[str, Any] | None = None,
) -> str:
    payload = {
        "latest_user_message": user_message,
        "briefing_conversation": list(conversation),
        "workflow_context": dict(workflow_context),
        "context_window_stats": dict(context_window_stats or {}),
        "output_schema": {
            "status": "needs_input | ready_for_approval",
            "understanding": "string",
            "next_question": {
                "field": "string",
                "question": "one highest-impact question",
                "choices": ["2-4 concise choices when useful"],
                "why": "short reason this question matters",
            },
            "hidden_questions": ["additional questions for trace/details only"],
            "questions": ["string"],
            "recommendations": ["string"],
            "draft_plan": {
                "objective": "string",
                "simulation_scope": ["geant4|tcad|ngspice"],
                "space_radiation": {
                    "model": "AP8/AE8 | none",
                    "particle": "proton|electron",
                    "solar_period": "min|max",
                    "flux_mode": "integral|differential",
                    "l_shell": "number or missing",
                    "bb0": "number or missing",
                    "orbit_inputs": {"altitude_km": "number", "inclination_deg": "number"},
                    "tle": ["line1", "line2"],
                    "geodetic_samples": [
                        {"latitude_deg": 0, "longitude_deg": 0, "altitude_km": 0, "iso_time": ""}
                    ],
                    "limitations": ["AP8/AE8 is static trapped-belt data"],
                },
                "geometry": {},
                "materials": [],
                "source": {},
                "physics": {},
                "scoring": [],
                "run_plan": {},
                "codegen_constraints": [],
            },
            "missing_critical_fields": ["string"],
            "assumptions": ["string"],
            "risks": ["string"],
            "final_query": "string",
            "proposed_command": {
                "name": "start_job",
                "args": {"query": "string", "run_mode": "strict"},
                "risk": "write",
                "status": "pending",
                "summary": "string",
            },
            "approval_request": {
                "requires_human_approval": True,
                "summary": "string",
                "risks": ["string"],
            },
        },
    }
    if compacted_briefing_memory:
        payload["compacted_briefing_memory"] = dict(compacted_briefing_memory)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_approved_summary_prompt(briefing_context: Mapping[str, Any]) -> str:
    payload = {
        "final_query": briefing_context.get("final_query", ""),
        "understanding": briefing_context.get("understanding", ""),
        "draft_plan": briefing_context.get("draft_plan", {}),
        "assumptions": briefing_context.get("assumptions", []),
        "risks": briefing_context.get("risks", []),
        "approval_request": briefing_context.get("approval_request", {}),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


async def _repair_briefing_json(
    *,
    gateway: Any,
    user_message: str,
    workflow_context: Mapping[str, Any],
    failed_result: Any,
) -> Any:
    return await gateway.call(
        task=ModelTask.SIMULATION_BRIEFING,
        tier=ModelTier.MAX,
        system_prompt=BRIEFING_JSON_REPAIR_PROMPT,
        user_prompt=json.dumps(
            {
                "latest_user_message": user_message,
                "workflow_context": dict(workflow_context),
                "failed_content": str(getattr(failed_result, "content", "") or ""),
                "failed_reasoning_content": str(
                    getattr(failed_result, "reasoning_content", "") or ""
                ),
                "required_output_schema": {
                    "status": "needs_input | ready_for_approval",
                    "understanding": "string",
                    "next_question": {
                        "field": "string",
                        "question": "one highest-impact question",
                        "choices": ["2-4 concise choices when useful"],
                        "why": "short reason",
                    },
                    "hidden_questions": ["string"],
                    "questions": ["string"],
                    "recommendations": ["string"],
                    "draft_plan": {},
                    "missing_critical_fields": ["string"],
                    "assumptions": ["string"],
                    "risks": ["string"],
                    "final_query": "string",
                    "proposed_command": {
                        "name": "start_job",
                        "args": {"query": "string", "run_mode": "strict"},
                        "risk": "write",
                        "status": "pending",
                        "summary": "string",
                    },
                    "approval_request": {
                        "requires_human_approval": True,
                        "summary": "string",
                        "risks": ["string"],
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        response_format="json",
        temperature=0.0,
        max_tokens=4096,
        metadata={"module_name": "simulation_briefing_repair"},
    )


def _briefing_json_from_result(result: Any) -> dict[str, Any]:
    parsed = getattr(result, "parsed_json", None)
    if isinstance(parsed, dict) and parsed:
        return parsed
    content_data = _parse_json_object(str(getattr(result, "content", "") or ""))
    if content_data:
        return content_data
    return _parse_json_object(str(getattr(result, "reasoning_content", "") or ""))


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        data = json.loads(content or "{}")
    except json.JSONDecodeError:
        data = _extract_json_object(content)
    return data if isinstance(data, dict) else {}


def _extract_json_object(content: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    while start >= 0:
        try:
            data, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        return data if isinstance(data, dict) else {}
    return {}


def _fallback_needs_input_briefing(user_message: str) -> dict[str, Any]:
    return {
        "status": "needs_input",
        "understanding": (
            "我收到你的仿真请求，但规划模型没有返回可解析的结构化简报。"
            "为避免误启动，需要先补充关键仿真信息。"
        ),
        "next_question": {
            "field": "simulation_goal",
            "question": "请补充本次仿真的主要对象、入射源/能量范围，以及希望输出的指标？",
            "choices": [
                "补充探测器、粒子、能量和输出",
                "先按默认参数生成可修改草案",
                "取消本次仿真规划",
            ],
            "why": "缺少结构化简报时不能安全启动仿真。",
        },
        "hidden_questions": [
            "几何和材料是什么？",
            "粒子类型、能量分布、事件数和方向是什么？",
            "需要统计哪些 scoring 输出？",
        ],
        "questions": ["请补充主要仿真对象、源项、能量范围和输出指标。"],
        "recommendations": ["先用小事件数验证几何、源项和 scoring。"],
        "draft_plan": {"latest_user_message": user_message},
        "missing_critical_fields": ["simulation_goal", "source", "scoring"],
        "assumptions": [],
        "risks": ["规划模型没有返回结构化 JSON，当前不会启动仿真。"],
        "final_query": "",
    }


def _clip_summary(value: Any, *, limit: int = 50) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:limit]


def _fallback_summary_text(briefing_context: Mapping[str, Any]) -> str:
    approval = briefing_context.get("approval_request")
    if isinstance(approval, Mapping) and approval.get("summary"):
        return str(approval.get("summary", ""))
    if briefing_context.get("final_query"):
        return str(briefing_context.get("final_query", ""))
    return str(briefing_context.get("understanding", ""))


def _turn_to_dict(turn: Mapping[str, str]) -> dict[str, str]:
    return {
        "role": str(turn.get("role", "")),
        "content": str(turn.get("content", "")),
    }


def _split_latest_turn(
    turns: Sequence[Mapping[str, str]],
    user_message: str,
) -> tuple[list[dict[str, str]], dict[str, str] | None]:
    normalized_latest = user_message.strip()
    if not turns:
        return [], None
    latest = _turn_to_dict(turns[-1])
    if latest["role"] == "user" and latest["content"].strip() == normalized_latest:
        return [_turn_to_dict(turn) for turn in turns[:-1]], latest
    return [_turn_to_dict(turn) for turn in turns], None


def _context_window_tokens(gateway: Any, tier: ModelTier) -> int:
    profile = getattr(gateway, "profiles", {}).get(tier)
    value = getattr(profile, "context_window_tokens", None)
    if isinstance(value, int) and value > 0:
        return value
    return _DEFAULT_CONTEXT_WINDOW_TOKENS


def _estimate_tokens(value: Any) -> int:
    text = json.dumps(value, ensure_ascii=False)
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    estimate = math.ceil(ascii_chars / 4) + non_ascii_chars
    return max(1, estimate)


def _list_value(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def _fallback_compacted_memory(
    older_history: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    text = " ".join(str(turn.get("content", "")) for turn in older_history)
    return {
        "stable_facts": [_clip_summary(text, limit=400)] if text else [],
        "answered_fields": {},
        "open_questions": [],
        "rejected_options": [],
        "latest_user_intent": "",
        "risk_notes": [],
    }
