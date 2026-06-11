from __future__ import annotations

from typing import Any

import pytest
from agent_core.intent.schemas import IntentResult
from agent_core.tui.controller import ControllerAction, TUIController


class _FakeService:
    def __init__(self) -> None:
        self.brief_calls: list[dict[str, Any]] = []
        self.started_jobs: list[dict[str, Any]] = []
        self.chat_messages: list[str] = []
        self.intent = IntentResult(
            intent="simulation_work",
            confidence=0.95,
            routing_reason="simulation request",
            normalized_user_query="我要仿真一个硅探测器",
            intent_detail="simulation_request",
            requires_job=True,
            requires_simulation_pipeline=True,
        )

    async def classify_intent(self, text: str) -> IntentResult:
        return self.intent

    async def brief_simulation(
        self,
        user_message: str,
        *,
        conversation: list[dict[str, str]],
    ) -> Any:
        self.brief_calls.append({"user_message": user_message, "conversation": conversation})

        class _Brief:
            status = "ready_for_approval"
            ready_for_approval = True
            understanding = "User wants a silicon detector simulation."
            questions: list[str] = []
            recommendations = ["Use FTFP_BERT for a first pass."]
            draft_plan = {"objective": "Measure deposited energy."}
            missing_critical_fields: list[str] = []
            assumptions = ["Default world is acceptable."]
            risks = ["Validate physics list."]
            final_query = "Build a Geant4 silicon detector deposited-energy simulation."
            proposed_command = {
                "name": "start_job",
                "args": {
                    "query": "Build a Geant4 silicon detector deposited-energy simulation.",
                    "run_mode": "acceptance",
                },
                "risk": "write",
                "status": "pending",
                "summary": "Start silicon detector simulation.",
            }
            approval_request = {
                "requires_human_approval": True,
                "summary": "Start silicon detector simulation.",
                "risks": ["Validate physics list."],
            }

            def summary_text(self) -> str:
                return self.approval_request["summary"]

            def model_dump(self, **kwargs: Any) -> dict[str, Any]:
                return {
                    "status": self.status,
                    "understanding": self.understanding,
                    "questions": self.questions,
                    "recommendations": self.recommendations,
                    "draft_plan": self.draft_plan,
                    "missing_critical_fields": self.missing_critical_fields,
                    "assumptions": self.assumptions,
                    "risks": self.risks,
                    "final_query": self.final_query,
                    "proposed_command": self.proposed_command,
                    "approval_request": self.approval_request,
                }

        return _Brief()

    async def chat(self, message: str) -> str:
        self.chat_messages.append(message)
        return "chat response"

    async def start_job(
        self,
        query: str,
        *,
        run_mode: str = "strict",
        auto_continue: bool = True,
        briefing_context: dict[str, Any] | None = None,
        reset_chat: bool = True,
    ) -> dict[str, Any]:
        self.started_jobs.append(
            {
                "query": query,
                "run_mode": run_mode,
                "auto_continue": auto_continue,
                "briefing_context": briefing_context,
                "reset_chat": reset_chat,
            }
        )
        return {"job_id": "job_1"}


class _SummaryService(_FakeService):
    async def summarize_approved_simulation_plan(
        self,
        briefing_context: dict[str, Any],
    ) -> dict[str, str]:
        assert "Build a Geant4 silicon detector" in briefing_context["final_query"]
        return {
            "zh": "硅探测器沉积能量仿真",
            "en": "Silicon detector edep simulation",
        }


class _GuidedQuestionService(_FakeService):
    async def brief_simulation(
        self,
        user_message: str,
        *,
        conversation: list[dict[str, str]],
    ) -> Any:
        self.brief_calls.append({"user_message": user_message, "conversation": conversation})
        if len(self.brief_calls) == 1:
            class _QuestionBrief:
                status = "needs_input"
                ready_for_approval = False
                understanding = "用户想做 He3 管中子探测仿真。"
                questions = ["你主要想模拟哪种入射中子？", "管长和半径？"]
                recommendations: list[str] = []
                draft_plan = {"objective": "He3 tube neutron response"}
                missing_critical_fields = ["source"]
                assumptions: list[str] = []
                risks: list[str] = []
                final_query = ""
                proposed_command = None
                approval_request = None
                hidden_questions = ["管长和半径？"]
                context_window_stats = {
                    "history_usage_ratio": 0.52,
                    "threshold": 0.75,
                    "compacted": False,
                    "context_window_tokens": 200_000,
                }

                class _NextQuestion:
                    field = "source"
                    question = "你主要想模拟哪种入射中子？"
                    choices = ["热中子", "单能快中子", "能谱源"]
                    why = "入射源决定物理列表。"

                next_question = _NextQuestion()

                def summary_text(self) -> str:
                    return "你主要想模拟哪种入射中子？\n1. 热中子\n2. 单能快中子\n3. 能谱源"

            return _QuestionBrief()

        return await super().brief_simulation(user_message, conversation=conversation)


@pytest.mark.asyncio
async def test_plain_simulation_request_enters_briefing_without_starting_job() -> None:
    service = _FakeService()
    controller = TUIController(service)

    result = await controller.handle_text("我要仿真一个硅探测器")

    assert result.action == ControllerAction.SHOW_BRIEFING
    assert controller.pending_brief is not None
    assert service.brief_calls[0]["user_message"] == "我要仿真一个硅探测器"
    assert service.started_jobs == []


@pytest.mark.asyncio
async def test_approval_starts_job_with_briefing_context() -> None:
    service = _FakeService()
    controller = TUIController(service)
    await controller.handle_text("我要仿真一个硅探测器")

    result = await controller.handle_text("确定")

    assert result.action == ControllerAction.START_OPERATION
    await result.operation
    assert service.started_jobs == [
            {
                "query": "Build a Geant4 silicon detector deposited-energy simulation.",
                "run_mode": "acceptance",
                "auto_continue": True,
                "briefing_context": controller.last_approved_briefing,
                "reset_chat": False,
        }
    ]
    assert service.started_jobs[0]["briefing_context"]["approval_request"][
        "requires_human_approval"
    ] is True
    assert service.started_jobs[0]["briefing_context"]["briefing_transcript"]
    assert controller.pending_brief is None


@pytest.mark.asyncio
async def test_approval_generates_lite_bilingual_short_task_summary() -> None:
    service = _SummaryService()
    controller = TUIController(service)
    await controller.handle_text("我要仿真一个硅探测器")

    result = await controller.handle_text("确定")
    await result.operation

    context = service.started_jobs[0]["briefing_context"]
    assert context["task_summary_short"] == {
        "zh": "硅探测器沉积能量仿真",
        "en": "Silicon detector edep simulation",
    }
    assert len(context["task_summary_short"]["zh"]) <= 50
    assert len(context["task_summary_short"]["en"]) <= 50


@pytest.mark.asyncio
async def test_modification_feedback_continues_briefing_instead_of_starting_job() -> None:
    service = _FakeService()
    controller = TUIController(service)
    await controller.handle_text("我要仿真一个硅探测器")

    result = await controller.handle_text("修改：粒子改成电子")

    assert result.action == ControllerAction.SHOW_BRIEFING
    assert service.started_jobs == []
    assert service.brief_calls[-1]["user_message"] == "修改：粒子改成电子"
    assert any(
        turn["role"] == "user" and "粒子改成电子" in turn["content"]
        for turn in service.brief_calls[-1]["conversation"]
    )


@pytest.mark.asyncio
async def test_guided_question_choice_number_is_resolved_before_next_briefing() -> None:
    service = _GuidedQuestionService()
    controller = TUIController(service)
    await controller.handle_text("我想要 he3 管仿真")

    result = await controller.handle_text("2")

    assert result.action == ControllerAction.SHOW_BRIEFING
    assert service.started_jobs == []
    assert service.brief_calls[-1]["user_message"] == "单能快中子"
    assert any(
        turn["role"] == "user" and turn["content"] == "单能快中子"
        for turn in service.brief_calls[-1]["conversation"]
    )


@pytest.mark.asyncio
async def test_controller_tracks_latest_copilot_context_usage() -> None:
    service = _GuidedQuestionService()
    controller = TUIController(service)

    await controller.handle_text("我想要 he3 管仿真")

    assert controller.latest_copilot_context_usage == {
        "history_usage_ratio": 0.52,
        "threshold": 0.75,
        "compacted": False,
        "context_window_tokens": 200_000,
    }


@pytest.mark.asyncio
async def test_chat_intent_uses_regular_chat() -> None:
    service = _FakeService()
    service.intent = IntentResult(
        intent="chat",
        confidence=0.9,
        routing_reason="question",
        normalized_user_query="解释一下物理列表",
        intent_detail="general_question",
    )
    controller = TUIController(service)

    result = await controller.handle_text("解释一下物理列表")

    assert result.action == ControllerAction.START_OPERATION
    await result.operation
    assert service.chat_messages == ["解释一下物理列表"]
    assert service.brief_calls == []
