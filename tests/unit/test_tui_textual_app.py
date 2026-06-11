from __future__ import annotations

import asyncio

import pytest
from agent_core.app import (
    ArtifactContent,
    ArtifactSummary,
    CopilotResponse,
    JobStatus,
    RadAgentAppService,
)
from agent_core.intent.schemas import IntentResult
from agent_core.tui.app import _THEMES, _css_for_theme, create_app_class

pytest.importorskip("textual")


async def _wait_for_controller_idle(app: object, pilot: object, *, timeout: float = 1.0) -> None:
    async def _wait() -> None:
        while getattr(app, "_controller_worker", None) is not None:
            await pilot.pause()
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait(), timeout=timeout)


async def _wait_for_operation_idle(app: object, pilot: object, *, timeout: float = 1.0) -> None:
    async def _wait() -> None:
        while getattr(app, "_operation_worker", None) is not None:
            await pilot.pause()
            await asyncio.sleep(0)

    await asyncio.wait_for(_wait(), timeout=timeout)


@pytest.mark.asyncio
async def test_textual_app_mounts_and_opens_help(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        header = app.query_one("#header")
        assert "RadAgent" in str(header.content)
        assert "phase:idle" in str(header.content)

        prompt = app.query_one("#prompt")
        footer = app.query_one("#footer")
        assert prompt.region.y + prompt.region.height < footer.region.y

        await pilot.press("f1")
        await pilot.pause()

        inspector = app.query_one("#inspector")
        assert "visible" in inspector.classes

        app.service._emit(
            "phase_started",
            status="running",
            phase="context",
            summary="Running context",
        )
        await pilot.pause()

        assert any(row.phase == "context" for row in app._rows)

        full_message = "**bold answer**\n\n- one\n- two"
        app.service._emit(
            "copilot_finished",
            status="success",
            summary=full_message[:10],
            payload={"message": full_message},
        )
        await pilot.pause()

        assert app._rows[-1].summary == full_message
        assert app.query("Markdown")


def test_default_theme_uses_slate_workstation_tokens_and_weak_borders() -> None:
    theme = _THEMES["slate-workstation"]
    css = _css_for_theme(theme)

    assert theme.screen_bg == "#0F1117"
    assert theme.surface_bg == "#151821"
    assert theme.composer_bg == "#10131A"
    assert theme.header_bg == "#151821"
    assert theme.header_fg == "#D8DEE9"
    assert theme.focus == "#C792EA"
    assert theme.border == "#2A2F3A"
    assert "border: solid #2A2F3A" in css
    assert "border: heavy" not in css
    assert "border-top" not in css


def test_ctrl_p_is_the_options_shortcut() -> None:
    app_cls = create_app_class()
    bindings = list(app_cls.BINDINGS)

    assert ("ctrl+comma", "show_settings", "Settings") not in bindings
    assert ("ctrl+p", "show_jobs", "Jobs") not in bindings
    assert any(
        getattr(binding, "key", None) == "ctrl+p"
        and getattr(binding, "action", None) == "show_options"
        and getattr(binding, "description", None) == "Options"
        for binding in bindings
    )


def test_ctrl_t_is_the_model_trace_shortcut() -> None:
    app_cls = create_app_class()
    bindings = list(app_cls.BINDINGS)

    assert any(
        getattr(binding, "key", None) == "ctrl+t"
        and getattr(binding, "action", None) == "show_trace"
        and getattr(binding, "description", None) == "Trace"
        for binding in bindings
    )


@pytest.mark.asyncio
async def test_textual_app_starts_without_font_copy_or_old_logo_block(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        assert app._rows[0].title == "RadAgent"
        summary = app._rows[0].summary
        assert "RadAgent" in summary
        assert "Models" in summary
        assert "█" not in summary
        assert "Recommended terminal font" not in summary
        assert "JetBrains Mono" not in summary
        assert r"\____" not in summary


@pytest.mark.asyncio
async def test_startup_renders_radagent_status_frame(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        first = app._rows[0]
        assert first.kind == "brand"
        assert "RadAgent" in first.summary
        assert "Geant4" in first.summary
        assert "TCAD" in first.summary
        assert "ngspice" in first.summary
        assert "Models" in first.summary
        assert "lite" in first.summary
        assert "pro" in first.summary
        assert "max" in first.summary


@pytest.mark.asyncio
async def test_task_context_marks_workflow_and_language_specific_summary(tmp_path) -> None:
    class _WorkflowService(RadAgentAppService):
        def get_status(self) -> JobStatus:
            return JobStatus(
                job_id="job_he3",
                user_query="Build a He3 tube neutron detector simulation.",
                status="running",
                current_phase="g4_modeling",
                current_phase_idx=3,
                completed_phases=["prepare_workspace", "context", "task_planning"],
                execution_mode="strict",
                run_mode="strict",
                workspace_root=str(tmp_path),
                state={
                    "task_summary_short": {
                        "zh": "He3管热中子探测效率仿真",
                        "en": "He3 tube thermal-neutron efficiency",
                    }
                },
            )

    app_cls = create_app_class()
    app = app_cls(service=_WorkflowService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        content = str(app.query_one("#task-context").content)
        assert "job_he3" in content
        assert "He3 tube thermal-neutron efficiency" in content
        assert "He3管热中子探测效率仿真" not in content
        assert "Task" in content
        assert "Job          job_he3" in content
        assert "State        running" in content
        assert "Phase        G4 modeling" in content
        assert "Workflow" in content
        assert "✓ Parse request" in content
        assert "✓ Prepare workspace" in content
        assert "✓ Load context" in content
        assert "● Plan simulation" in content
        assert "○ Generate macro / script" in content

        await app._dispatch_text("/options zh")
        await pilot.pause()

        content = str(app.query_one("#task-context").content)
        assert "He3管热中子探测效率仿真" in content
        assert "He3 tube thermal-neutron efficiency" not in content


@pytest.mark.asyncio
async def test_task_context_hides_simulation_summary_before_plan_approval(tmp_path) -> None:
    class _BriefingOnlyService(RadAgentAppService):
        def get_status(self) -> JobStatus:
            return JobStatus(
                job_id="job_pending",
                status="idle",
                current_phase="",
                current_phase_idx=0,
                completed_phases=[],
                execution_mode="strict",
                run_mode="strict",
                workspace_root=str(tmp_path),
                state={},
            )

    app_cls = create_app_class()
    app = app_cls(service=_BriefingOnlyService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        content = str(app.query_one("#task-context").content)
        assert "job_pending" in content
        assert "仿真" not in content
        assert "Particle" not in content
        assert "Energy" not in content


def _ready_guided_briefing() -> object:
    class _Briefing:
        status = "ready_for_approval"
        ready_for_approval = True
        understanding = "用户想做 He3 管中子探测仿真。"
        questions: list[str] = []
        recommendations = ["先用热中子源和小事件数验证几何。"]
        draft_plan = {"objective": "He3 tube neutron detection response"}
        missing_critical_fields: list[str] = []
        assumptions = ["默认采用热中子源。"]
        risks = ["He3 气压和管壁材料会影响探测效率。"]
        final_query = "Build a Geant4 He3 tube neutron detector simulation."
        approval_request = {
            "requires_human_approval": True,
            "summary": "Start He3 tube simulation.",
            "risks": risks,
        }

        def summary_text(self) -> str:
            return self.approval_request["summary"]

    return _Briefing()


@pytest.mark.asyncio
async def test_slow_briefing_shows_pending_row_before_model_returns(tmp_path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowBriefingService(RadAgentAppService):
        async def classify_intent(self, text: str) -> IntentResult:
            return IntentResult(
                intent="simulation_work",
                confidence=0.95,
                routing_reason="simulation request",
                normalized_user_query=text,
                intent_detail="simulation_request",
                requires_job=True,
                requires_simulation_pipeline=True,
            )

        async def brief_simulation(self, user_message: str, *, conversation: list[dict]) -> object:
            started.set()
            await release.wait()
            return _ready_guided_briefing()

    app_cls = create_app_class()
    app = app_cls(service=_SlowBriefingService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        dispatch_task = asyncio.create_task(app._dispatch_text("我想要 he3 管仿真"))
        await asyncio.wait_for(started.wait(), timeout=1)
        await pilot.pause()

        assert any(row.kind == "thinking" and row.status == "running" for row in app._rows)
        assert any(
            "分析仿真需求" in row.summary or "Analyzing" in row.summary
            for row in app._rows
        )

        release.set()
        await dispatch_task
        await _wait_for_controller_idle(app, pilot)
        await pilot.pause()
        assert any(row.title == "Simulation briefing" for row in app._rows)


@pytest.mark.asyncio
async def test_commands_remain_usable_while_copilot_response_is_pending(tmp_path) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class _SlowBriefingService(RadAgentAppService):
        async def classify_intent(self, text: str) -> IntentResult:
            return IntentResult(
                intent="simulation_work",
                confidence=0.95,
                routing_reason="simulation request",
                normalized_user_query=text,
                intent_detail="simulation_request",
                requires_job=True,
                requires_simulation_pipeline=True,
            )

        async def brief_simulation(self, user_message: str, *, conversation: list[dict]) -> object:
            started.set()
            await release.wait()
            return _ready_guided_briefing()

    app_cls = create_app_class()
    app = app_cls(service=_SlowBriefingService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt")
        prompt.value = "我想要 he3 管仿真"
        first_press = asyncio.create_task(pilot.press("enter"))
        option_press: asyncio.Task | None = None
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            await asyncio.sleep(0.05)

            prompt.value = "/options"
            option_press = asyncio.create_task(pilot.press("enter"))
            await asyncio.sleep(0.1)

            inspector = app.query_one("#inspector")
            assert "visible" in inspector.classes
            assert "Options" in str(inspector.content)
        finally:
            release.set()
            await asyncio.wait_for(first_press, timeout=1)
            if option_press is not None:
                await asyncio.wait_for(option_press, timeout=1)
            await _wait_for_controller_idle(app, pilot)


@pytest.mark.asyncio
async def test_prompt_lives_inside_display_frame_without_overlap(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        workbench = app.query_one("#workbench")
        timeline = app.query_one("#timeline")
        prompt = app.query_one("#prompt")
        footer = app.query_one("#footer")

        assert timeline.region.y >= workbench.region.y
        assert prompt.region.y > timeline.region.y + timeline.region.height
        assert (
            prompt.region.y + prompt.region.height
            <= workbench.region.y + workbench.region.height
        )
        assert prompt.region.y + prompt.region.height < footer.region.y


@pytest.mark.asyncio
async def test_options_command_switches_to_chinese_without_bilingual_footer(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        footer = app.query_one("#footer")
        assert "Ctrl+P options" in str(footer.content)
        assert "Ctrl+O artifacts" in str(footer.content)
        assert "产物" not in str(footer.content)

        await app._dispatch_text("/options zh")
        await pilot.pause()

        footer = app.query_one("#footer")
        inspector = app.query_one("#inspector")
        assert "Ctrl+P 选项" in str(footer.content)
        assert "Ctrl+O 产物" in str(footer.content)
        assert "artifacts" not in str(footer.content)
        assert "选项" in str(inspector.content)
        assert "JetBrains Mono" not in str(inspector.content)

        await app._dispatch_text("/settings en")
        await pilot.pause()

        footer = app.query_one("#footer")
        inspector = app.query_one("#inspector")
        assert "Ctrl+P options" in str(footer.content)
        assert "Ctrl+O artifacts" in str(footer.content)
        assert "产物" not in str(footer.content)
        assert "Options" in str(inspector.content)


@pytest.mark.asyncio
async def test_ctrl_p_opens_selectable_options_panel(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("ctrl+p")
        await pilot.pause()

        inspector = app.query_one("#inspector")
        assert "visible" in inspector.classes
        assert "Options" in str(inspector.content)
        assert ">" in str(inspector.content)
        assert "Language" in str(inspector.content)
        assert "Theme" in str(inspector.content)
        assert "slate-workstation" in str(inspector.content)
        assert "neon-lab" in str(inspector.content)
        assert "minimal-terminal" in str(inspector.content)
        assert "Logs" in str(inspector.content)
        assert "100k" in str(inspector.content)
        assert "200k" in str(inspector.content)
        assert "500k" in str(inspector.content)
        assert "1m" in str(inspector.content)


@pytest.mark.asyncio
async def test_options_panel_keyboard_updates_theme_and_language(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        await pilot.press("ctrl+p")
        await pilot.press("down")
        await pilot.press("right")
        await pilot.press("enter")
        await pilot.pause()

        assert app._theme_name == "neon-lab"
        assert "visible" not in app.query_one("#inspector").classes

        await pilot.press("ctrl+p")
        await pilot.pause()
        inspector = app.query_one("#inspector")
        assert "Theme" in str(inspector.content)
        assert "neon-lab" in str(inspector.content)

        await pilot.press("right")
        await pilot.press("enter")
        await pilot.pause()

        footer = app.query_one("#footer")
        assert "Ctrl+P 选项" in str(footer.content)


@pytest.mark.asyncio
async def test_timeline_static_rows_render_error_text_without_markup_crash(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        row_id = app._add_thinking_row()
        validation_error = (
            "1 validation error for SimulationBriefingResult\n"
            "approval_request.requires_human_approval\n"
            "  Input should be a valid dictionary "
            "[type=dict_type, input_value=False, input_type=bool]\n"
        )
        app._finish_thinking_row(row_id, status="error", summary=validation_error)
        await pilot.pause()

        assert app._rows[-1].summary == validation_error
        assert "validation error" in str(app._row_widgets[row_id].content)


@pytest.mark.asyncio
async def test_ctrl_t_opens_latest_model_trace(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        app.service._emit(
            "copilot_finished",
            status="success",
            summary="answer",
            payload={
                "message": "Use a thermal neutron validation run.",
                "reasoning_content": "checked He3 tube requirements",
            },
        )
        await pilot.pause()

        assert app._rows[-1].kind == "assistant_message"
        assert app._rows[-1].summary == "Use a thermal neutron validation run."

        await pilot.press("ctrl+t")
        await pilot.pause()

        inspector = app.query_one("#inspector")
        assert "visible" in inspector.classes
        assert "Model Trace" in str(inspector.content)
        assert "checked He3 tube requirements" in str(inspector.content)


@pytest.mark.asyncio
async def test_plain_chat_keeps_routing_events_out_of_main_timeline(tmp_path) -> None:
    class _FakeChatService(RadAgentAppService):
        async def classify_intent(self, text: str) -> IntentResult:
            result = IntentResult(
                intent="chat",
                confidence=0.92,
                routing_reason="question",
                normalized_user_query=text,
                intent_detail="general_question",
            )
            self._emit(
                "intent_classified",
                summary=str(result.intent),
                payload=result.model_dump(),
            )
            return result

        async def chat(self, message: str) -> CopilotResponse:
            started = self._emit(
                "copilot_started",
                status="running",
                summary=message,
                payload={"message": message},
            )
            finished = self._emit(
                "copilot_finished",
                status="success",
                summary="我是 Copilot。",
                payload={"message": "我是 Copilot。"},
            )
            return CopilotResponse(message="我是 Copilot。", events=[started, finished])

    service = _FakeChatService(workspace_root=tmp_path)
    app_cls = create_app_class()
    app = app_cls(service=service)

    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt")
        prompt.value = "你是谁"
        await pilot.press("enter")
        await pilot.pause()

        rendered_rows = [row.title for row in app._rows]
        assert "Chat" not in rendered_rows
        assert "Intent" not in rendered_rows
        assert any(row.kind == "user_message" and row.summary == "你是谁" for row in app._rows)
        assert any(
            row.kind == "assistant_message" and row.summary == "我是 Copilot。"
            for row in app._rows
        )

        await app._dispatch_text("/logs")
        await pilot.pause()

        inspector = app.query_one("#inspector")
        assert "intent_classified" in str(inspector.content)


@pytest.mark.asyncio
async def test_controller_failure_uses_copilot_display_name(tmp_path) -> None:
    class _BrokenController:
        async def handle_text(self, text: str) -> object:
            raise RuntimeError("offline")

    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()
        app.controller = _BrokenController()

        await app._dispatch_text("hello")
        await pilot.pause()

        assert app._rows[-1].title == "Copilot failed"


@pytest.mark.asyncio
async def test_textual_plain_simulation_request_uses_briefing_before_start() -> None:
    class _FakeService(RadAgentAppService):
        def __init__(self) -> None:
            super().__init__()
            self.started: list[dict] = []

        async def classify_intent(self, text: str) -> IntentResult:
            return IntentResult(
                intent="simulation_work",
                confidence=0.95,
                routing_reason="simulation request",
                normalized_user_query=text,
                intent_detail="simulation_request",
                requires_job=True,
                requires_simulation_pipeline=True,
            )

        async def brief_simulation(self, user_message: str, *, conversation: list[dict]) -> object:
            class _Brief:
                status = "ready_for_approval"
                ready_for_approval = True
                understanding = "User wants a detector simulation."
                questions: list[str] = []
                recommendations = ["Use a validation run first."]
                draft_plan = {"objective": "Measure dose."}
                missing_critical_fields: list[str] = []
                assumptions = ["Default world is acceptable."]
                risks = ["Validate physics list."]
                final_query = "Build a Geant4 detector dose simulation."
                approval_request = {
                    "requires_human_approval": True,
                    "summary": "Start detector dose simulation.",
                    "risks": ["Validate physics list."],
                }

                def summary_text(self) -> str:
                    return "Start detector dose simulation."

                def model_dump(self, **kwargs) -> dict:
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
                        "approval_request": self.approval_request,
                    }

            return _Brief()

        async def summarize_approved_simulation_plan(
            self,
            briefing_context: dict,
        ) -> dict[str, str]:
            return {
                "zh": "探测器剂量仿真",
                "en": "Detector dose simulation",
            }

        async def start_job(
            self,
            query: str,
            *,
            run_mode: str = "strict",
            auto_continue: bool = True,
            briefing_context: dict | None = None,
            reset_chat: bool = True,
        ) -> object:
            self.started.append(
                {
                    "query": query,
                    "briefing_context": briefing_context,
                    "reset_chat": reset_chat,
                }
            )
            return self.get_status()

    service = _FakeService()
    app_cls = create_app_class()
    app = app_cls(service=service)

    async with app.run_test() as pilot:
        await pilot.pause()
        prompt = app.query_one("#prompt")
        prompt.value = "我要仿真一个探测器"
        await pilot.press("enter")
        await pilot.pause()

        assert any(row.title == "Simulation briefing" for row in app._rows)
        assert service.started == []

        prompt.value = "确定"
        await pilot.press("enter")
        await _wait_for_controller_idle(app, pilot)
        await _wait_for_operation_idle(app, pilot)
        await pilot.pause()

        assert service.started
        assert service.started[0]["query"] == "Build a Geant4 detector dose simulation."
        assert service.started[0]["briefing_context"]["approval_request"][
            "requires_human_approval"
        ]
        assert service.started[0]["reset_chat"] is False


@pytest.mark.asyncio
async def test_workstation_commands_show_inspect_demo_and_history(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        await app._dispatch_text("/check")
        await pilot.pause()
        inspector = app.query_one("#inspector")
        assert "Tool Inspect" in str(inspector.content)
        assert "Geant4" in str(inspector.content)

        await app._dispatch_text("/demo geant4")
        await pilot.pause()
        content = str(app.query_one("#task-context").content)
        assert "demo-geant4" in content
        assert "State        preparing" in content
        assert "Phase        Prepare workspace" in content
        assert "Runtime" in content
        assert "Simulation" in content
        assert "Energy Deposit" in content

        await app._dispatch_text("/mode run")
        await pilot.pause()
        footer = app.query_one("#footer")
        prompt = app.query_one("#prompt")
        assert "RUN" in str(footer.content)
        assert "RUN >" in str(prompt.placeholder)

        await app._dispatch_text("/help")
        await app._dispatch_text("/artifacts")
        await pilot.press("ctrl+r")
        await pilot.pause()
        inspector = app.query_one("#inspector")
        assert "Command History" in str(inspector.content)
        assert "/help" in str(inspector.content)
        assert "/artifacts" in str(inspector.content)


@pytest.mark.asyncio
async def test_demo_autoplays_to_completed_state(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        await app._dispatch_text("/demo geant4")
        for _ in range(12):
            await pilot.pause(0.1)

        content = str(app.query_one("#task-context").content)
        assert "demo-geant4" in content
        assert "State        completed" in content
        assert "Phase        completed" in content


@pytest.mark.asyncio
async def test_history_search_and_binary_artifact_preview(tmp_path) -> None:
    class _ArtifactService(RadAgentAppService):
        def list_artifacts(self, job_id: str | None = None) -> list[ArtifactSummary]:
            return [
                ArtifactSummary(
                    job_id="job_1",
                    kind="plot",
                    path=str(tmp_path / "energy_deposit.png"),
                    size_bytes=320_000,
                )
            ]

        def read_artifact(self, path: str, *, max_chars: int = 200_000) -> ArtifactContent:
            return ArtifactContent(
                path=path,
                exists=True,
                kind="binary",
                size_bytes=320_000,
            )

    app_cls = create_app_class()
    app = app_cls(service=_ArtifactService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        await app._dispatch_text("/run electron dose")
        await app._dispatch_text("/check")
        await app._dispatch_text("/history electron")
        await pilot.pause()
        inspector = app.query_one("#inspector")
        assert "Command History" in str(inspector.content)
        assert "/run electron dose" in str(inspector.content)
        assert "/check" not in str(inspector.content)

        await app._dispatch_text("/open energy")
        await pilot.pause()
        inspector = app.query_one("#inspector")
        assert "Preview not available in terminal" in str(inspector.content)
        assert "energy_deposit.png" in str(inspector.content)
        assert "320000 bytes" in str(inspector.content)
