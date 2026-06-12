from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ControllerAction(StrEnum):
    START_OPERATION = "start_operation"
    SHOW_BRIEFING = "show_briefing"
    SHOW_MESSAGE = "show_message"


@dataclass(frozen=True)
class ControllerResult:
    action: ControllerAction
    title: str = ""
    summary: str = ""
    status: str = "info"
    operation: Any = None
    briefing: Any = None


@dataclass
class PendingBrief:
    original_request: str
    conversation: list[dict[str, str]]
    briefing: Any

    def briefing_context(self) -> dict[str, Any]:
        if hasattr(self.briefing, "model_dump"):
            data = self.briefing.model_dump(mode="json")
        else:
            data = {
                "status": getattr(self.briefing, "status", ""),
                "understanding": getattr(self.briefing, "understanding", ""),
                "questions": list(getattr(self.briefing, "questions", [])),
                "recommendations": list(getattr(self.briefing, "recommendations", [])),
                "draft_plan": dict(getattr(self.briefing, "draft_plan", {})),
                "missing_critical_fields": list(
                    getattr(self.briefing, "missing_critical_fields", [])
                ),
                "assumptions": list(getattr(self.briefing, "assumptions", [])),
                "risks": list(getattr(self.briefing, "risks", [])),
                "final_query": getattr(self.briefing, "final_query", ""),
                "proposed_command": getattr(self.briefing, "proposed_command", None),
                "approval_request": dict(getattr(self.briefing, "approval_request", {})),
            }
        data["original_request"] = self.original_request
        data["briefing_transcript"] = list(self.conversation)
        return data

    @property
    def final_query(self) -> str:
        return str(getattr(self.briefing, "final_query", "")).strip()


class TUIController:
    def __init__(self, service: Any) -> None:
        self.service = service
        self.pending_brief: PendingBrief | None = None
        self.last_approved_briefing: dict[str, Any] | None = None
        self.latest_copilot_context_usage: dict[str, Any] = {}

    async def handle_text(self, text: str) -> ControllerResult:
        stripped = text.strip()
        if not stripped:
            return ControllerResult(
                action=ControllerAction.SHOW_MESSAGE,
                title="Input required",
                summary="Enter a message or command.",
                status="warning",
            )

        if self.pending_brief is not None:
            return await self._handle_briefing_reply(stripped)

        intent = await self.service.classify_intent(stripped)
        if getattr(intent, "intent", "") == "simulation_work":
            return await self._continue_briefing(
                stripped,
                original_request=stripped,
                conversation=[{"role": "user", "content": stripped}],
            )

        return ControllerResult(
            action=ControllerAction.START_OPERATION,
            operation=self.service.chat(stripped),
            title="Chat",
            summary=stripped[:120],
            status="running",
        )

    async def start_simulation_briefing(self, query: str) -> ControllerResult:
        stripped = query.strip()
        if not stripped:
            return ControllerResult(
                action=ControllerAction.SHOW_MESSAGE,
                title="Input required",
                summary="Enter a simulation request.",
                status="warning",
            )
        return await self._continue_briefing(
            stripped,
            original_request=stripped,
            conversation=[{"role": "user", "content": stripped}],
        )

    async def _handle_briefing_reply(self, text: str) -> ControllerResult:
        assert self.pending_brief is not None
        if _is_cancel(text):
            self.pending_brief = None
            return ControllerResult(
                action=ControllerAction.SHOW_MESSAGE,
                title="Briefing cancelled",
                summary="未启动仿真任务。",
                status="warning",
            )

        if _is_approval(text):
            pending = self.pending_brief
            if not getattr(pending.briefing, "ready_for_approval", False):
                return ControllerResult(
                    action=ControllerAction.SHOW_MESSAGE,
                    title="Briefing incomplete",
                    summary="当前方案还未进入可批准状态，请继续补充信息。",
                    status="warning",
                )
            if not pending.final_query:
                return ControllerResult(
                    action=ControllerAction.SHOW_MESSAGE,
                    title="Briefing incomplete",
                    summary="当前方案还没有 final_query，不能启动。",
                    status="warning",
            )
            briefing_context = pending.briefing_context()
            summary_method = getattr(
                self.service,
                "summarize_approved_simulation_plan",
                None,
            )
            if callable(summary_method):
                try:
                    summary = await summary_method(briefing_context)
                except Exception:
                    summary = {}
                normalized_summary = _normalize_task_summary_short(summary)
                if normalized_summary:
                    briefing_context["task_summary_short"] = normalized_summary
            if self.latest_copilot_context_usage:
                briefing_context["context_window_stats"] = dict(
                    self.latest_copilot_context_usage
                )
            command_args = _command_args(briefing_context)
            query = str(command_args.get("query") or pending.final_query)
            run_mode = str(
                command_args.get("run_mode") or getattr(self.service, "execution_mode", "strict")
            )
            self.last_approved_briefing = briefing_context
            self.pending_brief = None
            return ControllerResult(
                action=ControllerAction.START_OPERATION,
                operation=self.service.start_job(
                    query,
                    run_mode=run_mode,
                    auto_continue=True,
                    briefing_context=briefing_context,
                    reset_chat=False,
                ),
                title="Starting simulation",
                summary=query[:160],
                status="running",
            )

        answer_text = _guided_answer_text(self.pending_brief.briefing, text)
        conversation = [
            *self.pending_brief.conversation,
            {"role": "user", "content": answer_text},
        ]
        return await self._continue_briefing(
            answer_text,
            original_request=self.pending_brief.original_request,
            conversation=conversation,
        )

    async def _continue_briefing(
        self,
        user_message: str,
        *,
        original_request: str,
        conversation: list[dict[str, str]],
    ) -> ControllerResult:
        briefing = await self.service.brief_simulation(
            user_message,
            conversation=conversation,
        )
        self.latest_copilot_context_usage = _context_usage_from_briefing(briefing)
        summary = (
            briefing.summary_text()
            if hasattr(briefing, "summary_text")
            else str(getattr(briefing, "understanding", ""))
        )
        conversation = [
            *conversation,
            {"role": "assistant", "content": summary},
        ]
        self.pending_brief = PendingBrief(
            original_request=original_request,
            conversation=conversation,
            briefing=briefing,
        )
        return ControllerResult(
            action=ControllerAction.SHOW_BRIEFING,
            title="Simulation briefing",
            summary=summary,
            status="success" if getattr(briefing, "ready_for_approval", False) else "warning",
            briefing=briefing,
        )


def _is_approval(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {
        "ok",
        "yes",
        "y",
        "approve",
        "approved",
        "confirm",
        "confirmed",
        "start",
        "go",
        "确定",
        "确认",
        "批准",
        "同意",
        "启动",
        "开始",
        "就这样",
        "按这个来",
    }


def _is_cancel(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"cancel", "stop", "no", "n", "取消", "停止", "不启动", "算了"}


def _command_args(briefing_context: dict[str, Any]) -> dict[str, Any]:
    command = briefing_context.get("proposed_command")
    if not isinstance(command, dict):
        return {}
    args = command.get("args")
    return args if isinstance(args, dict) else {}


def _guided_answer_text(briefing: Any, text: str) -> str:
    choices = _next_question_choices(briefing)
    normalized = text.strip()
    if choices and normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(choices):
            return choices[index]
    return text


def _next_question_choices(briefing: Any) -> list[str]:
    question = getattr(briefing, "next_question", None)
    if isinstance(question, dict):
        choices = question.get("choices", [])
    else:
        choices = getattr(question, "choices", [])
    return [str(choice) for choice in choices or []]


def _clip_short_text(value: Any, *, limit: int = 50) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:limit]


def _normalize_task_summary_short(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {
            key: _clip_short_text(value.get(key))
            for key in ("zh", "en")
            if _clip_short_text(value.get(key))
        }
    text = _clip_short_text(value)
    if not text:
        return {}
    return {"zh": text, "en": text}


def _context_usage_from_briefing(briefing: Any) -> dict[str, Any]:
    value = getattr(briefing, "context_window_stats", {})
    if isinstance(value, dict):
        return dict(value)
    return {}
