from __future__ import annotations

import asyncio
import inspect
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from agent_core.app import JobStatus, RadAgentAppService
from agent_core.tui.adapters import (
    event_to_row,
    render_artifacts_table,
    render_command_palette,
    render_confirmation_review,
    render_error_state,
    render_header,
    render_job_detail,
    render_jobs_table,
    render_markdown_row,
    render_row,
    render_startup_status,
    render_task_context,
    render_tool_inspect,
    row_css_class,
    status_to_header,
)
from agent_core.tui.commands import CommandParseError, input_mode_for_text, parse_command
from agent_core.tui.controller import ControllerAction, TUIController
from agent_core.tui.i18n import DEFAULT_LANGUAGE, label, language_name, parse_language
from agent_core.tui.models import TimelineRow


class TextualNotInstalledError(RuntimeError):
    """Raised when the optional Textual dependency is not installed."""


@dataclass(frozen=True)
class _Theme:
    screen_bg: str
    surface_bg: str
    row_bg: str
    composer_bg: str
    header_bg: str
    header_fg: str
    border: str
    focus: str
    text: str
    muted: str
    success: str
    running: str
    warning: str
    error: str


@dataclass(frozen=True)
class _TextualModules:
    app: Any
    binding: Any
    compose_result: Any
    containers: Any
    widgets: Any


_THEMES: dict[str, _Theme] = {
    "slate-workstation": _Theme(
        screen_bg="#0F1117",
        surface_bg="#151821",
        row_bg="#151821",
        composer_bg="#10131A",
        header_bg="#151821",
        header_fg="#D8DEE9",
        border="#2A2F3A",
        focus="#C792EA",
        text="#D8DEE9",
        muted="#8B93A6",
        success="#7FD1A0",
        running="#56B6C2",
        warning="#EBCB8B",
        error="#F07178",
    ),
    "neon-lab": _Theme(
        screen_bg="#070A12",
        surface_bg="#10131D",
        row_bg="#141A28",
        composer_bg="#0C1018",
        header_bg="#10131D",
        header_fg="#E6EAF2",
        border="#293044",
        focus="#C792EA",
        text="#E6EAF2",
        muted="#8791A8",
        success="#7FD1A0",
        running="#56B6C2",
        warning="#EBCB8B",
        error="#F07178",
    ),
    "minimal-terminal": _Theme(
        screen_bg="#0C0D0F",
        surface_bg="#111214",
        row_bg="#151619",
        composer_bg="#0F1012",
        header_bg="#111214",
        header_fg="#DADDE3",
        border="#2B2D33",
        focus="#DADDE3",
        text="#DADDE3",
        muted="#858B96",
        success="#A8D5BA",
        running="#B7C4D6",
        warning="#D8C58A",
        error="#E28C8C",
    ),
}
_THEME_NAMES = tuple(_THEMES)
_THEME_ALIASES = {
    "radagent": "neon-lab",
    "slate": "slate-workstation",
    "mono": "minimal-terminal",
}
_OPTION_ROWS = ("language", "theme", "copilot_model", "copilot_window")
_COMMON_COPILOT_MODELS = (
    "mimo-v2.5-pro",
    "mimo-v2.5",
    "mimo-v2.5-max",
    "mimo-v2.5-lite",
)
_CONTEXT_WINDOW_SEQUENCE = (100_000, 200_000, 500_000, 1_000_000)
_THINKING_FRAMES = ("[.  ]", "[.. ]", "[...]")
_COMPOSER_MODES = {
    "ask": "ASK",
    "run": "RUN",
    "cmd": "CMD",
    "inspect": "INSPECT",
    "artifact": "ARTIFACT",
    "config": "CONFIG",
}
_CONFIRMATION_APPROVAL_TEXTS = {
    "ok",
    "yes",
    "y",
    "approve",
    "approved",
    "confirm",
    "confirmed",
    "start",
    "go",
    "确认",
    "确定",
    "批准",
    "同意",
    "启动",
    "开始",
}
_DEMO_PROFILES = {
    "geant4": "Geant4 detector validation",
    "tcad": "TCAD device sweep",
    "ngspice": "ngspice circuit run",
    "neutron-ct": "Neutron CT reconstruction",
    "electron-dose": "Electron dose deposition",
}
_DEMO_STEPS = (
    ("preparing", "prepare_workspace", []),
    ("checking", "context", ["prepare_workspace"]),
    ("generating", "g4_codegen", ["prepare_workspace", "context", "task_planning", "g4_modeling"]),
    (
        "running",
        "gate",
        [
            "prepare_workspace",
            "context",
            "task_planning",
            "g4_modeling",
            "human_confirmation",
            "g4_codegen",
            "patch",
        ],
    ),
    (
        "analyzing",
        "artifact",
        [
            "prepare_workspace",
            "context",
            "task_planning",
            "g4_modeling",
            "human_confirmation",
            "g4_codegen",
            "patch",
            "gate",
        ],
    ),
    (
        "reporting",
        "report",
        [
            "prepare_workspace",
            "context",
            "task_planning",
            "g4_modeling",
            "human_confirmation",
            "g4_codegen",
            "patch",
            "gate",
            "artifact",
        ],
    ),
    (
        "completed",
        "",
        [
            "prepare_workspace",
            "context",
            "task_planning",
            "g4_modeling",
            "human_confirmation",
            "g4_codegen",
            "patch",
            "gate",
            "artifact",
            "report",
        ],
    ),
)


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point for the Textual RadAgent TUI."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(_usage())
        return 0
    execution_mode = "strict"
    theme_name = "slate-workstation"
    try:
        execution_mode = _option_value(argv, "--mode", execution_mode)
        theme_name = _normalize_theme_name(_option_value(argv, "--theme", theme_name))
    except ValueError:
        print(_usage(), file=sys.stderr)
        return 2
    if execution_mode not in {"strict", "test", "acceptance", "production"}:
        print(_usage(), file=sys.stderr)
        return 2
    try:
        app_cls = create_app_class(theme=theme_name)
    except TextualNotInstalledError:
        print(
            "RadAgent TUI requires the optional Textual dependency.\n"
            "Install it with: pip install -e '.[tui]'",
            file=sys.stderr,
        )
        return 1

    app = app_cls(execution_mode=execution_mode)
    app.run()
    return 0


def _option_value(argv: Sequence[str], name: str, default: str) -> str:
    if name not in argv:
        return default
    index = argv.index(name)
    try:
        return argv[index + 1]
    except IndexError as exc:
        raise ValueError(name) from exc


def _usage() -> str:
    return (
        "Usage: radagent-tui [--mode strict|test|acceptance|production] "
        "[--theme slate-workstation|neon-lab|minimal-terminal]"
    )


def _normalize_theme_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = _THEME_ALIASES.get(normalized, normalized)
    if normalized not in _THEMES:
        raise ValueError(value)
    return normalized


def _show_event_in_timeline(event: Any) -> bool:
    """Return whether a service event belongs in the main user timeline."""
    return getattr(event, "event_type", "") not in {
        "intent_classified",
    }


def _css_for_theme(theme: _Theme) -> str:
    return f"""
        Screen {{
            background: {theme.screen_bg};
            color: {theme.text};
        }}

        #header {{
            height: 1;
            padding: 0 1;
            background: {theme.header_bg};
            color: {theme.header_fg};
            text-style: bold;
        }}

        #workbench {{
            height: 1fr;
            padding: 1 2;
            border: solid {theme.border};
            background: {theme.surface_bg};
        }}

        #main-split {{
            height: 1fr;
        }}

        #conversation-pane {{
            height: 1fr;
            width: 1fr;
            padding: 0 1 0 0;
        }}

        #timeline {{
            height: 1fr;
            padding: 0 0 1 0;
            background: {theme.surface_bg};
        }}

        #task-context {{
            width: 34;
            height: 1fr;
            padding: 1;
            border: solid {theme.border};
            background: {theme.composer_bg};
            color: {theme.text};
        }}

        .row {{
            height: auto;
            margin: 0 0 1 0;
            padding: 0 1;
        }}

        .role-user {{
            background: {theme.row_bg};
            color: {theme.text};
        }}

        .role-agent {{
            background: {theme.composer_bg};
            color: {theme.success};
            text-style: bold;
        }}

        .role-run,
        .role-tool,
        .role-system {{
            color: {theme.muted};
        }}

        .role-review {{
            background: {theme.row_bg};
            color: {theme.warning};
        }}

        .role-error {{
            background: {theme.row_bg};
            color: {theme.error};
        }}

        .status-running {{
            color: {theme.running};
        }}

        .status-success {{
            color: {theme.success};
        }}

        .status-warning {{
            color: {theme.warning};
        }}

        .status-error {{
            color: {theme.error};
        }}

        #composer {{
            height: 4;
            padding: 1 0 0 0;
            background: {theme.surface_bg};
        }}

        #prompt {{
            height: 3;
            width: 1fr;
            background: {theme.composer_bg};
            color: {theme.text};
            border: solid {theme.border};
        }}

        #prompt:focus {{
            border: solid {theme.focus};
        }}

        #footer {{
            height: 1;
            padding: 0 2;
            margin-top: 1;
            color: {theme.muted};
            background: {theme.screen_bg};
        }}

        #inspector {{
            dock: right;
            width: 46;
            padding: 1;
            border: solid {theme.focus};
            background: {theme.composer_bg};
            color: {theme.text};
            display: none;
            text-style: bold;
        }}

        #inspector.visible {{
            display: block;
        }}
    """


def create_app_class(*, theme: str = "slate-workstation") -> type[Any]:
    """Create the Textual app class after optional dependencies are available."""
    theme = _normalize_theme_name(theme)
    textual = _load_textual()
    textual_app = textual.app
    binding = textual.binding
    horizontal = textual.containers.Horizontal
    vertical = textual.containers.Vertical
    vertical_scroll = textual.containers.VerticalScroll
    input_widget = textual.widgets.Input
    markdown = textual.widgets.Markdown
    static = textual.widgets.Static
    css = _css_for_theme(_THEMES[theme])

    class RadAgentTUI(textual_app):  # type: ignore[misc, valid-type]
        """Terminal-native RadAgent workbench."""

        TITLE = "RadAgent"
        ENABLE_COMMAND_PALETTE = False
        CSS = css
        BINDINGS = [
            binding("ctrl+l", "focus_composer", "Input"),
            binding("ctrl+p", "show_options", "Options"),
            binding("ctrl+i", "toggle_inspector", "Inspect"),
            binding("ctrl+t", "show_trace", "Trace"),
            binding("ctrl+o", "show_artifacts", "Artifacts"),
            binding("up", "history_previous", show=False, priority=True),
            binding("down", "history_next", show=False, priority=True),
            binding("left", "options_decrement", show=False, priority=True),
            binding("right", "options_increment", show=False, priority=True),
            binding("enter", "options_apply", show=False, priority=True),
            binding("ctrl+r", "show_history", "History"),
            binding("escape", "close_inspector", "Close"),
            binding("f1", "show_help", "Help"),
            binding("ctrl+c", "interrupt_or_quit", "Stop"),
        ]

        def __init__(
            self,
            *,
            service: RadAgentAppService | None = None,
            execution_mode: str = "strict",
        ) -> None:
            super().__init__()
            self.service = service or RadAgentAppService(execution_mode=execution_mode)
            self.controller = TUIController(self.service)
            self._busy = False
            self._operation_worker: Any = None
            self._controller_worker: Any = None
            self._controller_thinking_id = ""
            self._thinking_frame_index = 0
            self._rows: list[TimelineRow] = []
            self._row_widgets: dict[str, Any] = {}
            self._trace_snippets: list[str] = []
            self._language = DEFAULT_LANGUAGE
            self._theme_name = theme
            self._options_open = False
            self._options_selected = 0
            self._options_draft_language = self._language
            self._options_draft_theme = self._theme_name
            self._options_model_candidates = list(_COMMON_COPILOT_MODELS)
            self._options_original_copilot_model = _COMMON_COPILOT_MODELS[0]
            self._options_draft_copilot_model = _COMMON_COPILOT_MODELS[0]
            self._options_original_copilot_window = 1_000_000
            self._options_draft_copilot_window = 1_000_000
            self._command_history: list[str] = []
            self._history_index: int | None = None
            self._composer_mode = "ASK"
            self._demo_status: JobStatus | None = None
            self._demo_profile = ""
            self._demo_title = ""
            self._demo_step_index = 0
            self._demo_worker: Any = None

        def compose(self) -> Any:
            yield static("", id="header")
            with vertical(id="workbench"):
                with horizontal(id="main-split"):
                    with vertical(id="conversation-pane"):
                        yield vertical_scroll(id="timeline")
                        with horizontal(id="composer"):
                            yield input_widget(
                                placeholder=label("prompt.placeholder", self._language),
                                id="prompt",
                            )
                    yield static("", id="task-context", markup=False)
            yield static("", id="footer")
            yield static("", id="inspector", markup=False)

        def on_mount(self) -> None:
            self._refresh_header()
            self._refresh_footer()
            self._refresh_task_context()
            self._add_system_row(
                label("ready.title", self._language),
                self._startup_summary(),
                kind="brand",
            )
            self.run_worker(self._listen_events(), name="radagent-events", exclusive=False)
            self.set_interval(0.28, self._tick_thinking_rows)
            self.action_focus_composer()

        async def _listen_events(self) -> None:
            async for event in self.service.subscribe_events():
                self._add_event_row(event)
                self._refresh_header()
                self._refresh_task_context()

        async def on_input_submitted(self, event: Any) -> None:
            text = event.value.strip()
            event.input.value = ""
            self._history_index = None
            self._refresh_footer()
            await self._dispatch_text(text)

        def on_input_changed(self, event: Any) -> None:
            text = str(event.value)
            if text.strip().startswith("/") or self._composer_mode in {"ASK", "CMD"}:
                self._composer_mode = input_mode_for_text(text)
            if text.strip().startswith("/") and len(text.strip()) <= 20:
                self._show_panel("Command Palette", render_command_palette(text).splitlines()[2:])
            self._refresh_footer()

        async def _dispatch_text(self, text: str) -> None:
            self._remember_command_history(text.strip())
            if not text.startswith("/") and text != "?":
                if (
                    getattr(self.controller, "pending_brief", None) is None
                    and self._needs_confirmation()
                    and _is_confirmation_approval_text(text)
                ):
                    self._submit_confirmation_approval()
                    return
                if self._composer_mode == "RUN":
                    await self._dispatch_text(f"/run {text}")
                    return
                if self._composer_mode == "INSPECT":
                    self._show_tool_inspect()
                    return
                if self._composer_mode == "ARTIFACT":
                    self._open_artifact_or_collection(text)
                    return
                if self._composer_mode == "CONFIG":
                    self._show_options(text)
                    return
                await self._dispatch_controller_text(text)
                return

            try:
                command = parse_command(text)
            except CommandParseError as exc:
                self._add_system_row("Command error", str(exc), status="warning")
                return

            match command.name:
                case "chat":
                    self._start_operation(self.service.chat(command.args))
                case "approve":
                    self._submit_confirmation_approval()
                case "run":
                    self._demo_status = None
                    self._start_operation(
                        self.service.start_job(
                            command.args,
                            run_mode=self.service.execution_mode,
                            auto_continue=True,
                            briefing_context=_tui_run_briefing_context(command.args),
                        )
                    )
                case "check" | "inspect":
                    self._show_tool_inspect()
                case "status":
                    self._show_status()
                case "history":
                    self._show_history(command.args)
                case "step":
                    self._start_operation(self.service.step())
                case "resume":
                    try:
                        self.service.resume_job(command.args)
                    except Exception as exc:
                        self._add_system_row("Resume failed", str(exc), status="error")
                    else:
                        self._refresh_header()
                        self._refresh_task_context()
                case "jobs":
                    self._show_jobs()
                case "job":
                    self._show_job(command.args)
                case "retry":
                    self._retry_job(command.args)
                case "artifacts":
                    self._show_artifacts()
                case "artifact":
                    self._show_artifact(command.args)
                case "open":
                    self._open_artifact_or_collection(command.args)
                case "report":
                    self._show_report()
                case "demo":
                    self._start_demo(command.args)
                case "gates":
                    self._show_gates()
                case "memory":
                    self._show_memory()
                case "confirm":
                    if _is_confirmation_approval_text(command.args):
                        self._submit_confirmation_approval()
                    else:
                        self._show_confirmation()
                case "reject":
                    self._submit_confirmation_decision(
                        "reject",
                        command.args,
                        title="Confirmation rejected",
                    )
                case "ask-more":
                    self._submit_confirmation_decision(
                        "ask_more",
                        command.args,
                        title="Confirmation needs more input",
                    )
                case "credibility":
                    self._show_credibility()
                case "model":
                    if command.args:
                        self._update_model_config(command.args)
                    else:
                        self._show_model_config()
                case "options":
                    self._show_options(command.args)
                case "logs":
                    self._show_logs()
                case "projects":
                    self._show_projects()
                case "project":
                    self._switch_project(command.args)
                case "revise":
                    self._create_revision(command.args)
                case "revisions":
                    self._show_revisions()
                case "revision":
                    self._show_revision(command.args)
                case "accept-revision":
                    self._start_operation(self.service.accept_revision(command.args))
                case "reject-revision":
                    self._reject_revision(command.args)
                case "build":
                    self._start_operation(self.service.build_generated_code())
                case "simulate":
                    events = int(command.args) if command.args else 1000
                    self._start_operation(self.service.run_simulation(events=events))
                case "mode":
                    self._set_composer_mode(command.args)
                case "help":
                    self._show_help()
                case "exit":
                    self.exit()
                case _:
                    self._add_system_row("Command error", f"Unhandled command: {command.name}")

        async def _dispatch_controller_text(self, text: str) -> None:
            if self._busy:
                self._add_system_row("Busy", "Wait for the current operation to finish.", "warning")
                return
            if self._controller_worker is not None:
                self._add_system_row(
                    "Copilot busy",
                    (
                        "Copilot is still responding. Commands such as /options "
                        "and /logs remain available."
                    ),
                    "warning",
                )
                return
            thinking_id = self._add_thinking_row() if text.strip() else ""
            self._controller_thinking_id = thinking_id
            self._controller_worker = self.run_worker(
                self._run_controller_text(text, thinking_id),
                name="radagent-controller",
                exclusive=True,
                group="radagent-controller",
            )
            self._refresh_header()

        async def _run_controller_text(self, text: str, thinking_id: str) -> None:
            try:
                result = await self.controller.handle_text(text)
            except Exception as exc:
                self._finish_thinking_row(thinking_id, status="error", summary=str(exc))
                self._add_system_row("Copilot failed", str(exc), "error")
                return
            finally:
                self._controller_worker = None
                self._controller_thinking_id = ""
                self._refresh_header()

            self._apply_controller_result(result, thinking_id)

        def _apply_controller_result(self, result: Any, thinking_id: str) -> None:
            self._finish_thinking_row(thinking_id)
            if result.action == ControllerAction.SHOW_BRIEFING:
                self._add_briefing_row(result.briefing)
                self._refresh_task_context()
                return
            if result.action == ControllerAction.START_OPERATION:
                self._start_operation(result.operation)
                return
            self._add_system_row(result.title or "Message", result.summary, result.status)
            self._refresh_task_context()

        def _start_operation(self, operation: Any) -> None:
            if self._busy:
                operation.close()
                self._add_system_row("Busy", "Wait for the current operation to finish.", "warning")
                return
            self._busy = True
            self._refresh_header()
            self._refresh_task_context()
            self._operation_worker = self.run_worker(
                self._run_operation(operation),
                name="radagent-operation",
                exclusive=True,
                group="radagent-operation",
            )

        async def _run_operation(self, operation: Any) -> None:
            try:
                result = await operation
                await self._handle_operation_result(result)
            except Exception as exc:
                self._add_system_row("Operation failed", str(exc), "error")
            finally:
                self._busy = False
                self._operation_worker = None
                self._refresh_header()
                self._refresh_task_context()

        async def _handle_operation_result(self, result: Any) -> None:
            query = _simulation_briefing_query_from_result(result)
            if not query:
                return
            controller_result = await self.controller.start_simulation_briefing(query)
            self._apply_controller_result(controller_result, "")

        def _add_event_row(self, event: Any) -> None:
            self._remember_trace(getattr(event, "payload", {}))
            if not _show_event_in_timeline(event):
                return
            self._append_row(event_to_row(event))

        def _add_system_row(
            self,
            title: str,
            summary: str = "",
            status: str = "info",
            kind: str = "system",
        ) -> None:
            row = TimelineRow(
                id=f"system:{len(self._rows)}",
                kind=kind,
                status=status,
                title=title,
                summary=summary,
            )
            self._append_row(row)

        def _add_thinking_row(self) -> str:
            row = TimelineRow(
                id=f"thinking:{len(self._rows)}",
                kind="thinking",
                status="running",
                title="Copilot",
                summary=self._t("thinking.analyzing"),
                payload={"activity_frame": _THINKING_FRAMES[self._thinking_frame_index]},
            )
            self._append_row(row)
            return row.id

        def _tick_thinking_rows(self) -> None:
            running_rows = [
                index
                for index, row in enumerate(self._rows)
                if row.kind == "thinking" and row.status == "running"
            ]
            if not running_rows:
                return
            self._thinking_frame_index = (
                self._thinking_frame_index + 1
            ) % len(_THINKING_FRAMES)
            frame = _THINKING_FRAMES[self._thinking_frame_index]
            for index in running_rows:
                row = self._rows[index]
                payload = dict(row.payload)
                payload["activity_frame"] = frame
                updated = replace(row, payload=payload)
                self._rows[index] = updated
                widget = self._row_widgets.get(row.id)
                if widget is not None and hasattr(widget, "update"):
                    widget.update(render_row(updated))

        def _finish_thinking_row(
            self,
            row_id: str,
            *,
            status: str = "success",
            summary: str | None = None,
        ) -> None:
            if not row_id:
                return
            for index, row in enumerate(self._rows):
                if row.id != row_id:
                    continue
                updated = replace(
                    row,
                    status=status,
                    summary=summary if summary is not None else self._t("thinking.done"),
                )
                self._rows[index] = updated
                widget = self._row_widgets.get(row_id)
                if widget is not None and hasattr(widget, "update"):
                    widget.update(render_row(updated))
                return

        def _add_briefing_row(self, briefing: Any) -> None:
            self._remember_briefing_trace(briefing)
            lines = [
                str(getattr(briefing, "understanding", "")),
            ]
            ready = bool(getattr(briefing, "ready_for_approval", False))
            next_question = getattr(briefing, "next_question", None)
            questions = list(getattr(briefing, "questions", []) or [])
            recommendations = list(getattr(briefing, "recommendations", []) or [])
            missing = list(getattr(briefing, "missing_critical_fields", []) or [])
            assumptions = list(getattr(briefing, "assumptions", []) or [])
            risks = list(getattr(briefing, "risks", []) or [])
            question_text = str(_briefing_value(next_question, "question", "") or "")
            choices = list(_briefing_value(next_question, "choices", []) or [])
            if question_text:
                lines.extend(["", "Question:", question_text])
                lines.extend(f"{index}. {choice}" for index, choice in enumerate(choices, start=1))
            elif questions:
                lines.extend(["", "Question:", f"- {questions[0]}"])
            if recommendations:
                lines.extend(
                    ["", "Recommendations:", *[f"- {item}" for item in recommendations[:8]]]
                )
            if missing and (ready or not question_text):
                lines.extend(["", "Missing:", *[f"- {item}" for item in missing[:8]]])
            if assumptions and ready:
                lines.extend(["", "Assumptions:", *[f"- {item}" for item in assumptions[:8]]])
            if risks and ready:
                lines.extend(["", "Risks:", *[f"- {item}" for item in risks[:8]]])
            if ready:
                summary = (
                    briefing.summary_text()
                    if hasattr(briefing, "summary_text")
                    else str(getattr(briefing, "final_query", ""))
                )
                lines.extend(
                    [
                        "",
                        "Approval required:",
                        summary,
                        "",
                        "输入 确定/批准 启动，输入 修改:<意见> 继续打磨，输入 取消 放弃。",
                    ]
                )
            row = TimelineRow(
                id=f"briefing:{len(self._rows)}",
                kind="confirmation",
                status="success" if getattr(briefing, "ready_for_approval", False) else "warning",
                title="Simulation briefing",
                summary="\n".join(line for line in lines if line is not None),
                payload={
                    "final_query": getattr(briefing, "final_query", ""),
                    "ready_for_approval": getattr(briefing, "ready_for_approval", False),
                },
            )
            self._append_row(row)

        def _remember_briefing_trace(self, briefing: Any) -> None:
            lines: list[str] = []
            hidden = list(getattr(briefing, "hidden_questions", []) or [])
            assumptions = list(getattr(briefing, "assumptions", []) or [])
            risks = list(getattr(briefing, "risks", []) or [])
            if hidden:
                lines.extend(["Hidden questions:", *[f"- {item}" for item in hidden[:12]]])
            if assumptions:
                lines.extend(["Assumptions:", *[f"- {item}" for item in assumptions[:12]]])
            if risks:
                lines.extend(["Risks:", *[f"- {item}" for item in risks[:12]]])
            if lines:
                self._trace_snippets.append("\n".join(lines))

        def _append_row(self, row: TimelineRow) -> None:
            self._rows.append(row)
            timeline = self.query_one("#timeline", vertical_scroll)
            if row.kind == "assistant_message" and row.summary:
                widget = markdown(
                    render_markdown_row(row),
                    classes=row_css_class(row),
                )
            else:
                widget = static(render_row(row), classes=row_css_class(row), markup=False)
            timeline.mount(widget)
            self._row_widgets[row.id] = widget
            scroll_end = getattr(timeline, "scroll_end", None)
            if callable(scroll_end):
                scroll_end(animate=False)

        def _refresh_header(self) -> None:
            try:
                project = str(self.service.current_project().get("slug", "default"))
            except Exception:
                project = "default"
            header = status_to_header(self.service.get_status(), project=project)
            busy = "  busy" if self._busy or self._controller_worker is not None else ""
            self.query_one("#header", static).update(render_header(header) + busy)

        def _refresh_footer(self) -> None:
            mode = self._composer_mode
            self.query_one("#footer", static).update(
                f"{mode}  {label('footer', self._language)}"
            )
            prompt = self.query_one("#prompt", input_widget)
            prompt.placeholder = self._prompt_placeholder()

        def _refresh_task_context(self) -> None:
            status = self._status_with_controller_usage()
            self.query_one("#task-context", static).update(
                render_task_context(status, language=self._language)
            )

        def _status_with_controller_usage(self) -> JobStatus:
            if self._demo_status is not None:
                return self._demo_status
            status = self.service.get_status()
            usage = getattr(self.controller, "latest_copilot_context_usage", {})
            if not usage:
                return status
            state = dict(status.state)
            state.setdefault("copilot_context_usage", usage)
            return status.model_copy(update={"state": state})

        def _startup_summary(self) -> str:
            try:
                startup = self.service.get_startup_status()
            except Exception:
                return label("brand.ready", self._language)
            return render_startup_status(startup)

        def _prompt_placeholder(self) -> str:
            if self._composer_mode == "RUN":
                return "RUN > Describe a simulation request"
            if self._composer_mode == "CMD":
                return "CMD > /run /check /open /report /help"
            if self._composer_mode == "INSPECT":
                return "INSPECT > /check tools"
            if self._composer_mode == "ARTIFACT":
                return "ARTIFACT > /artifacts or /open report"
            if self._composer_mode == "CONFIG":
                return "CONFIG > /options or /model key=value"
            return label("prompt.placeholder", self._language)

        def _t(self, key: str) -> str:
            return label(key, self._language)

        def _show_panel(
            self,
            title: str,
            lines: list[str],
            *,
            options_panel: bool = False,
        ) -> None:
            if not options_panel:
                self._options_open = False
                self.refresh_bindings()
            body = "\n".join([title, "", *lines])
            inspector = self.query_one("#inspector", static)
            inspector.update(body)
            inspector.add_class("visible")

        def _show_jobs(self) -> None:
            jobs = self.service.list_jobs(include_all_projects=True)
            rendered = render_jobs_table(jobs)
            self._show_panel(self._t("jobs.title"), rendered.splitlines()[2:])

        def _show_job(self, job_id: str) -> None:
            job = self.service.get_job(job_id)
            rendered = render_job_detail(job)
            self._show_panel("Job Detail", rendered.splitlines()[2:])

        def _retry_job(self, job_id: str) -> None:
            try:
                self.service.resume_job(job_id)
            except Exception as exc:
                self._show_panel(
                    "Retry",
                    render_error_state(
                        f"Cannot retry job: {job_id}",
                        suggestions=[str(exc), "Run /jobs", "Check the job id"],
                    ).splitlines(),
                )
                return
            self._demo_status = None
            self._start_operation(self.service.run_until_blocked())

        def _show_artifacts(self) -> None:
            artifacts = self.service.list_artifacts()
            rendered = render_artifacts_table(list(artifacts))
            self._show_panel(self._t("artifacts.title"), rendered.splitlines()[2:])

        def _show_artifact(self, path: str) -> None:
            artifact = self.service.read_artifact(path, max_chars=8000)
            if not artifact.exists:
                self._show_panel(
                    "Artifact",
                    render_error_state(
                        f"Artifact not found: {path}",
                        suggestions=["Run /artifacts", "Check the active job", "Run /open report"],
                    ).splitlines(),
                )
                return
            if artifact.kind == "binary":
                self._show_panel(
                    "Artifact",
                    [
                        "Preview not available in terminal",
                        f"Path: {artifact.path}",
                        f"{artifact.size_bytes} bytes",
                    ],
                )
                return
            content = artifact.text
            if artifact.truncated:
                content += "\n\n[truncated]"
            self._show_panel("Artifact", content.splitlines()[:200])

        def _open_artifact_or_collection(self, value: str) -> None:
            target = value.strip()
            if not target:
                self._show_artifacts()
                return
            artifacts = self.service.list_artifacts()
            match = next(
                (
                    item
                    for item in artifacts
                    if target.lower() in (item.kind or "").lower()
                    or target.lower() in item.path.lower()
                ),
                None,
            )
            if match is None:
                self._show_panel(
                    "Open",
                    render_error_state(
                        f"No artifact matches: {target}",
                        suggestions=["Run /artifacts", "Use /artifact <path>", "Run /report"],
                    ).splitlines(),
                )
                return
            self._show_artifact(match.path)

        def _show_report(self) -> None:
            artifacts = self.service.list_artifacts()
            report = next(
                (
                    item
                    for item in artifacts
                    if "report" in (item.kind or "").lower()
                    or item.path.lower().endswith((".md", ".html", ".pdf"))
                ),
                None,
            )
            if report is None:
                self._show_panel(
                    "Report",
                    render_error_state(
                        "No report artifact is available.",
                        suggestions=[
                            "Run /step until report generation",
                            "Run /artifacts",
                            "Run /demo geant4 for a safe preview",
                        ],
                    ).splitlines(),
                )
                return
            self._show_artifact(report.path)

        def _show_gates(self) -> None:
            gates = self.service.get_gate_results()
            if not gates:
                self._show_panel("Gates", ["No gate results for the active job."])
                return
            lines = [
                (
                    f"{gate.get('status', 'unknown'):8} "
                    f"{gate.get('gate_id', '?'):>2} "
                    f"{gate.get('name', gate.get('gate', 'gate'))}: "
                    f"{gate.get('message', '')}"
                )
                for gate in gates[:40]
            ]
            self._show_panel("Gates", lines)

        def _show_memory(self) -> None:
            context = self.service.get_workflow_context()
            lines = [
                f"{item.source:8} {item.key}: {item.summary}"
                for item in context.memory[:30]
            ]
            self._show_panel("Memory", lines or ["No workflow memory for the active job."])

        def _show_confirmation(self) -> None:
            review = self.service.get_confirmation_review()
            rendered = render_confirmation_review(review)
            self._show_panel("Confirmation", rendered.splitlines()[2:])

        def _needs_confirmation(self) -> bool:
            try:
                status = self.service.get_status()
            except Exception:
                return False
            return bool(
                status.needs_confirmation
                or (status.job_id and status.current_phase == "human_confirmation")
            )

        def _submit_confirmation_approval(self) -> None:
            if not self._needs_confirmation():
                self._add_system_row(
                    "Confirmation",
                    "No active human confirmation is pending.",
                    "warning",
                )
                return
            response = {
                "user_decision": "approve",
                "edits": [],
                "user_notes": "Approved from RadAgent TUI.",
            }
            self._add_system_row("Confirmation submitted", "approve", "running")
            self._start_operation(
                self.service.submit_confirmation(response, auto_continue=True)
            )

        def _submit_confirmation_decision(
            self,
            decision: str,
            notes: str,
            *,
            title: str,
        ) -> None:
            if not self._needs_confirmation():
                self._add_system_row(
                    "Confirmation",
                    "No active human confirmation is pending.",
                    "warning",
                )
                return
            response = {
                "user_decision": decision,
                "edits": [],
                "user_notes": notes.strip(),
            }
            self._add_system_row(title, response["user_notes"], "warning")
            self._start_operation(
                self.service.submit_confirmation(response, auto_continue=False)
            )

        def _show_credibility(self) -> None:
            report = self.service.get_credibility_report()
            if not report:
                self._show_panel("Credibility", ["No credibility gate result yet."])
                return
            lines = [
                f"status: {report.get('status', 'unknown')}",
                f"level: {report.get('credibility_level', 'unknown')}",
                f"confidence: {report.get('confidence', '')}",
                f"message: {report.get('message', '')}",
            ]
            warnings = report.get("warnings", [])
            if warnings:
                lines.extend(["", "Warnings:", *[f"- {item}" for item in warnings[:8]]])
            self._show_panel("Credibility", lines)

        def _create_revision(self, request: str) -> None:
            try:
                revision = self.service.create_revision(request)
            except Exception as exc:
                self._add_system_row("Revision failed", str(exc), "error")
                return
            self._add_system_row(
                "Revision created",
                str(revision.get("revision_id", "")),
                "success",
            )
            self._show_revision(str(revision.get("revision_id", "")))

        def _show_revisions(self) -> None:
            revisions = self.service.list_revisions()
            if not revisions:
                self._show_panel("Revisions", ["No revisions for the active job."])
                return
            lines = [
                (
                    f"{item.get('status', 'unknown'):10} "
                    f"{item.get('revision_id', '')}  "
                    f"{item.get('user_request', '')}"
                )
                for item in revisions[:30]
            ]
            self._show_panel("Revisions", lines)

        def _show_revision(self, revision_id: str) -> None:
            revisions = self.service.list_revisions()
            revision = next(
                (item for item in revisions if item.get("revision_id") == revision_id),
                None,
            )
            if not revision:
                self._show_panel("Revision", [f"Revision not found: {revision_id}"])
                return
            lines = [
                f"id: {revision.get('revision_id', '')}",
                f"status: {revision.get('status', '')}",
                f"patch: {revision.get('patch_status', '')}",
                f"candidate: {revision.get('candidate_project_dir', '')}",
                "",
                str(revision.get("user_request", "")),
            ]
            errors = revision.get("errors", [])
            if errors:
                lines.extend(["", "Errors:", *[f"- {item}" for item in errors[:8]]])
            self._show_panel("Revision", lines)

        def _reject_revision(self, revision_id: str) -> None:
            try:
                self.service.reject_revision(revision_id)
            except Exception as exc:
                self._add_system_row("Revision reject failed", str(exc), "error")
                return
            self._add_system_row("Revision rejected", revision_id, "warning")

        def _show_model_config(self) -> None:
            config = self.service.get_model_config()
            lines = [
                f"env: {config.env_path}",
                "set: /model url=<base_url> key=<api_key> lite=<model> pro=<model> max=<model>",
                "",
            ]
            for tier_name in ("lite", "pro", "max"):
                tier = config.tiers.get(tier_name)
                if tier is None:
                    continue
                key_status = "configured" if tier.api_key_configured else "missing"
                thinking = "on" if tier.thinking_default else "off"
                lines.extend(
                    [
                        f"[{tier.tier}] {tier.model_name}",
                        f"  url: {tier.base_url or 'unset'}",
                        f"  key: {tier.api_key_env} ({key_status})",
                        (
                            f"  tokens: {tier.max_tokens}  timeout: {tier.timeout_s}s  "
                            f"window: {tier.context_window_tokens}  thinking: {thinking}"
                        ),
                    ]
                )
            self._show_panel("Model Config", lines)

        def _update_model_config(self, args: str) -> None:
            try:
                update = _parse_model_config_args(args)
                config = self.service.update_model_config(update)
            except Exception as exc:
                self._add_system_row("Model config failed", str(exc), "error")
                return
            pro = config.tiers.get("pro")
            summary = pro.model_name if pro else "updated"
            self._add_system_row("Model config updated", summary, "success")
            self._show_model_config()

        def _show_logs(self) -> None:
            events = self.service.recent_events(30)
            if not events:
                self._show_panel("Logs", ["No events yet."])
                return
            lines = [
                f"{event.status:8} {event.event_type:28} {event.summary}"
                for event in events
            ]
            self._show_panel("Logs", lines)

        def _show_trace(self) -> None:
            if not self._trace_snippets:
                self._show_panel("Model Trace", ["No model trace has been reported yet."])
                return
            self._show_panel("Model Trace", self._trace_snippets[-20:])

        def _remember_trace(self, payload: Any) -> None:
            if not isinstance(payload, dict):
                return
            trace = str(payload.get("reasoning_content") or "").strip()
            if trace:
                self._trace_snippets.append(trace)

        def _show_projects(self) -> None:
            projects = self.service.list_projects()
            lines = [
                f"{project.get('slug', ''):20} {project.get('name', '')}"
                for project in projects[:30]
            ]
            self._show_panel("Projects", lines or ["No projects found."])

        def _switch_project(self, value: str) -> None:
            try:
                project = self.service.set_current_project(value)
            except Exception as exc:
                self._add_system_row("Project switch failed", str(exc), "error")
                return
            self._add_system_row("Project switched", str(project.get("slug", value)), "success")
            self._refresh_header()

        def _show_status(self) -> None:
            status = self.service.get_status()
            lines = [
                f"status: {status.status}",
                f"job: {status.job_id or 'no-job'}",
                f"phase: {status.current_phase or 'idle'}",
                f"mode: {status.run_mode}",
                f"confirmation: {'yes' if status.needs_confirmation else 'no'}",
            ]
            self._show_panel(self._t("status.title"), lines)

        def _show_tool_inspect(self) -> None:
            try:
                startup = self.service.get_startup_status()
            except Exception as exc:
                self._show_panel(
                    "Tool Inspect",
                    render_error_state(
                        "Unable to inspect runtime tools.",
                        suggestions=[str(exc), "Check environment settings", "Run /logs"],
                    ).splitlines(),
                )
                return
            rendered = render_tool_inspect(startup)
            self._show_panel("Tool Inspect", rendered.splitlines()[2:])

        def _set_composer_mode(self, value: str) -> None:
            selected = value.strip().lower()
            self._composer_mode = _COMPOSER_MODES[selected]
            self._refresh_footer()
            self._add_system_row("Mode", self._composer_mode, "success")

        def _start_demo(self, profile: str) -> None:
            selected = profile.strip().lower()
            title = _DEMO_PROFILES.get(selected)
            if title is None:
                self._show_panel(
                    "Demo Mode",
                    render_error_state(
                        f"Unknown demo profile: {profile}",
                        suggestions=[
                            "/demo geant4",
                            "/demo tcad",
                            "/demo ngspice",
                            "/demo neutron-ct",
                            "/demo electron-dose",
                        ],
                    ).splitlines(),
                )
                return
            self._demo_profile = selected
            self._demo_title = title
            self._demo_step_index = 0
            self._demo_status = self._build_demo_status()
            if self._demo_worker is not None:
                self._demo_worker.cancel()
            self._demo_worker = self.run_worker(
                self._play_demo_steps(),
                name="radagent-demo",
                exclusive=True,
                group="radagent-demo",
            )
            for summary in (
                "Preparing workspace",
                "Checking tools",
                "Generating macro",
                "Running simulation",
                "Analyzing output",
                "Generating report",
            ):
                self._add_system_row("Demo", summary, "running")
            self._refresh_header()
            self._refresh_task_context()

        async def _play_demo_steps(self) -> None:
            while self._demo_profile and self._demo_step_index < len(_DEMO_STEPS) - 1:
                await asyncio.sleep(0.05)
                self._advance_demo_step()
            self._demo_worker = None

        def _advance_demo_step(self) -> None:
            if not self._demo_profile:
                return
            self._demo_step_index = min(self._demo_step_index + 1, len(_DEMO_STEPS) - 1)
            self._demo_status = self._build_demo_status()
            self._refresh_header()
            self._refresh_task_context()

        def _build_demo_status(self) -> JobStatus:
            state, phase, completed = _DEMO_STEPS[self._demo_step_index]
            phase_idx = 0
            if phase:
                from agent_core.pipeline import PIPELINE_PHASES

                phase_idx = PIPELINE_PHASES.index(phase)
            else:
                phase_idx = len(completed)
            selected = self._demo_profile
            title = self._demo_title
            return JobStatus(
                job_id=f"demo-{selected}",
                user_query=title,
                status=state,
                current_phase=phase,
                current_phase_idx=phase_idx,
                completed_phases=list(completed),
                execution_mode=self.service.execution_mode,
                run_mode="demo",
                workspace_root=str(self.service.workspace.root),
                state={
                    "task_summary_short": {"en": title, "zh": title},
                    "runtime_monitor": {
                        "cpu_percent": 18,
                        "memory_gb": 2.1,
                        "disk_free_gb": 42,
                        "events_done": 32000,
                        "events_total": 100000,
                        "speed": "1200 evt/s",
                    },
                    "simulation_summary": {
                        "Particle": "electron" if "electron" in selected else "neutron",
                        "Energy": "7 MeV" if "electron" in selected else "thermal",
                        "Target": "aluminum" if "electron" in selected else "silicon",
                        "Detector": "silicon",
                        "Events": "100000",
                    },
                    "ascii_chart": {
                        "title": "Energy Deposit",
                        "bins": [
                            ("0 cm", 1.0),
                            ("2 cm", 0.8),
                            ("4 cm", 0.5),
                            ("6 cm", 0.2),
                            ("8 cm", 0.05),
                        ],
                    },
                },
            )

        def _show_options(self, args: str = "") -> None:
            if args:
                try:
                    self._apply_options_argument(args)
                except ValueError as exc:
                    self._add_system_row("Command error", str(exc), status="warning")
                    return
                self._add_system_row(self._t("options.updated"), args.strip(), "success")
            self._open_options()

        def _apply_options_argument(self, args: str) -> None:
            value = args.strip()
            normalized = value.lower()
            if normalized.startswith("theme="):
                normalized = normalized.partition("=")[2].strip()
            try:
                theme_name = _normalize_theme_name(normalized)
            except ValueError:
                theme_name = ""
            if theme_name:
                self._apply_theme(theme_name)
                return
            self._language = parse_language(value)
            self._refresh_footer()
            self._refresh_task_context()

        def _open_options(self) -> None:
            self._options_open = True
            self._options_selected = 0
            self._options_draft_language = self._language
            self._options_draft_theme = self._theme_name
            self._load_options_model_config()
            self.refresh_bindings()
            self._render_options_panel()

        def _load_options_model_config(self) -> None:
            try:
                config = self.service.get_model_config()
            except Exception:
                self._options_model_candidates = list(_COMMON_COPILOT_MODELS)
                self._options_original_copilot_model = self._options_model_candidates[0]
                self._options_draft_copilot_model = self._options_model_candidates[0]
                self._options_original_copilot_window = 1_000_000
                self._options_draft_copilot_window = 1_000_000
                return

            models = {
                tier_name: str(getattr(tier, "model_name", "") or "")
                for tier_name, tier in config.tiers.items()
            }
            self._options_model_candidates = _copilot_model_candidates(models)
            pro = config.tiers.get("pro")
            pro_model = str(getattr(pro, "model_name", "") or "")
            if not pro_model:
                pro_model = self._options_model_candidates[0]
            self._options_original_copilot_model = pro_model
            self._options_draft_copilot_model = pro_model
            self._options_original_copilot_window = int(
                getattr(pro, "context_window_tokens", 1_000_000) or 1_000_000
            )
            self._options_draft_copilot_window = self._options_original_copilot_window

        def _render_options_panel(self) -> None:
            lines = [
                self._option_line(
                    0,
                    self._t("options.language"),
                    language_name(self._options_draft_language),
                ),
                self._option_line(
                    1,
                    self._t("options.theme"),
                    f"{self._options_draft_theme}  ({' | '.join(_THEME_NAMES)})",
                ),
                self._option_line(
                    2,
                    "Copilot Model",
                    (
                        f"{self._options_draft_copilot_model}  "
                        f"({' | '.join(self._options_model_candidates)})"
                    ),
                ),
                self._option_line(
                    3,
                    "Copilot Window",
                    (
                        f"{_format_context_window(self._options_draft_copilot_window)}  "
                        f"({_context_window_option_labels()})"
                    ),
                ),
                "",
                self._t("options.controls"),
                self._t("options.context_window"),
                "",
                *_model_config_help_lines(),
                "",
                self._t("options.ctrl_o"),
                self._t("options.jobs"),
                self._t("options.logs"),
            ]
            self._show_panel(self._t("options.title"), lines, options_panel=True)

        def _option_line(self, index: int, title: str, value: str) -> str:
            cursor = ">" if self._options_selected == index else " "
            return f"{cursor} {title:<10} {value}"

        def _change_option_selection(self, delta: int) -> None:
            self._options_selected = (self._options_selected + delta) % len(_OPTION_ROWS)
            self._render_options_panel()

        def _change_option_value(self, delta: int) -> None:
            option = _OPTION_ROWS[self._options_selected]
            if option == "language":
                languages = list(type(self._language))
                index = languages.index(self._options_draft_language)
                self._options_draft_language = languages[(index + delta) % len(languages)]
            elif option == "theme":
                index = _THEME_NAMES.index(self._options_draft_theme)
                self._options_draft_theme = _THEME_NAMES[(index + delta) % len(_THEME_NAMES)]
            elif option == "copilot_model":
                self._options_draft_copilot_model = _cycle_string_option(
                    self._options_draft_copilot_model,
                    self._options_model_candidates,
                    delta,
                )
            elif option == "copilot_window":
                self._options_draft_copilot_window = _cycle_context_window(
                    self._options_draft_copilot_window,
                    delta,
                )
            self._render_options_panel()

        def _apply_options_draft(self) -> None:
            updates: list[str] = []
            if self._language != self._options_draft_language:
                self._language = self._options_draft_language
                self._refresh_footer()
                self._refresh_task_context()
                updates.append(language_name(self._language))
            if self._theme_name != self._options_draft_theme:
                self._apply_theme(self._options_draft_theme)
                updates.append(self._theme_name)
            model_update: dict[str, Any] = {}
            if self._options_original_copilot_model != self._options_draft_copilot_model:
                model_update["pro_model"] = self._options_draft_copilot_model
            if self._options_original_copilot_window != self._options_draft_copilot_window:
                model_update["pro_context_window_tokens"] = (
                    self._options_draft_copilot_window
                )
            if model_update:
                try:
                    self.service.update_model_config(model_update)
                except Exception as exc:
                    self._add_system_row("Model config failed", str(exc), "error")
                    return
                if "pro_model" in model_update:
                    updates.append(f"Copilot {self._options_draft_copilot_model}")
                if "pro_context_window_tokens" in model_update:
                    updates.append(
                        f"Window {_format_context_window(self._options_draft_copilot_window)}"
                    )
            self._options_open = False
            self.refresh_bindings()
            self.query_one("#inspector", static).remove_class("visible")
            self.action_focus_composer()
            self._add_system_row(
                self._t("options.updated"),
                ", ".join(updates) if updates else self._t("options.current"),
                "success",
            )

        def _apply_theme(self, theme_name: str) -> None:
            self._theme_name = theme_name
            new_css = _css_for_theme(_THEMES[theme_name])
            self.__class__.CSS = new_css
            try:
                app_path = inspect.getfile(self.__class__)
            except (TypeError, OSError):
                app_path = ""
            self.stylesheet.add_source(
                new_css,
                read_from=(app_path, f"{self.__class__.__name__}.CSS"),
                is_default_css=False,
            )
            self.refresh_css(animate=False)

        def _show_help(self) -> None:
            self._show_panel(
                self._t("commands.title"),
                [
                    "/run <query>",
                    "/chat <message>",
                    "/jobs",
                    "/job <job_id>",
                    "/resume <job_id>",
                    "/retry <job_id>",
                    "/check",
                    "/artifacts",
                    "/artifact <path>",
                    "/open [artifact|report]",
                    "/report",
                    "/demo <geant4|tcad|ngspice|neutron-ct|electron-dose>",
                    "/mode <ask|run|cmd|inspect|artifact|config>",
                    "/gates",
                    "/memory",
                    "/confirm",
                    "/reject <reason>",
                    "/ask-more <question>",
                    "/credibility",
                    "/model [url=... key=... lite=... pro=... max=...]",
                    "/logs",
                    "/build",
                    "/simulate [events]",
                    "/options [en|zh]",
                    "/projects",
                    "/project <slug-or-id>",
                    "/revise <request>",
                    "/revisions",
                    "/revision <revision_id>",
                    "/accept-revision <revision_id>",
                    "/reject-revision <revision_id>",
                    "/help",
                    "/exit",
                ],
            )

        def action_focus_composer(self) -> None:
            self.query_one("#prompt", input_widget).focus()

        def action_show_jobs(self) -> None:
            self._show_jobs()

        def action_show_artifacts(self) -> None:
            self._show_artifacts()

        def action_toggle_inspector(self) -> None:
            inspector = self.query_one("#inspector", static)
            if "visible" in inspector.classes:
                self._options_open = False
                self.refresh_bindings()
                inspector.remove_class("visible")
            else:
                self._show_tool_inspect()

        def action_close_inspector(self) -> None:
            self._options_open = False
            self.refresh_bindings()
            self.query_one("#inspector", static).remove_class("visible")

        def action_show_help(self) -> None:
            self._show_help()

        def action_show_options(self) -> None:
            self._show_options()

        def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
            if action.startswith("options_"):
                return self._options_open
            return True

        def action_history_previous(self) -> None:
            if self._options_open:
                self._change_option_selection(-1)
                return
            self._apply_history_delta(-1)

        def action_history_next(self) -> None:
            if self._options_open:
                self._change_option_selection(1)
                return
            self._apply_history_delta(1)

        def action_options_decrement(self) -> None:
            self._change_option_value(-1)

        def action_options_increment(self) -> None:
            self._change_option_value(1)

        def action_options_apply(self) -> None:
            self._apply_options_draft()

        def action_show_trace(self) -> None:
            self._show_trace()

        def action_show_history(self) -> None:
            self._show_history("")

        def _show_history(self, query: str = "") -> None:
            normalized = query.strip().lower()
            history = self._command_history
            if normalized:
                history = [item for item in history if normalized in item.lower()]
            lines = history[-20:] or ["No command history yet."]
            self._show_panel("Command History", lines)

        def _remember_command_history(self, text: str) -> None:
            if not text:
                return
            if self._command_history and self._command_history[-1] == text:
                return
            self._command_history.append(text)

        def _apply_history_delta(self, delta: int) -> None:
            if not self._command_history:
                return
            if self._history_index is None:
                self._history_index = len(self._command_history)
            self._history_index = max(
                0,
                min(len(self._command_history) - 1, self._history_index + delta),
            )
            prompt = self.query_one("#prompt", input_widget)
            prompt.value = self._command_history[self._history_index]

        def action_interrupt_or_quit(self) -> None:
            if self._controller_worker is not None:
                self._controller_worker.cancel()
                self._controller_worker = None
                self._finish_thinking_row(
                    self._controller_thinking_id,
                    status="warning",
                    summary="Copilot response was cancelled.",
                )
                self._controller_thinking_id = ""
                self._add_system_row("Interrupted", "Copilot response was cancelled.", "warning")
                self._refresh_header()
                self._refresh_task_context()
                return
            if self._operation_worker is not None:
                self._operation_worker.cancel()
                self._operation_worker = None
                self._busy = False
                self._add_system_row("Interrupted", "Current operation was cancelled.", "warning")
                self._refresh_header()
                self._refresh_task_context()
                return
            self.exit()

    return RadAgentTUI


def _parse_model_config_args(args: str) -> dict[str, Any]:
    aliases = {
        "url": "base_url",
        "base_url": "base_url",
        "key": "api_key",
        "api_key": "api_key",
        "api_key_env": "api_key_env",
        "lite": "lite_model",
        "lite_model": "lite_model",
        "pro": "pro_model",
        "pro_model": "pro_model",
        "max": "max_model",
        "max_model": "max_model",
        "lite_tokens": "lite_max_tokens",
        "pro_tokens": "pro_max_tokens",
        "max_tokens": "max_max_tokens",
        "lite_window": "lite_context_window_tokens",
        "pro_window": "pro_context_window_tokens",
        "max_window": "max_context_window_tokens",
        "lite_timeout": "lite_timeout_s",
        "pro_timeout": "pro_timeout_s",
        "max_timeout": "max_timeout_s",
    }
    integer_fields = {
        "lite_max_tokens",
        "max_max_tokens",
        "pro_max_tokens",
    }
    context_window_fields = {
        "lite_context_window_tokens",
        "max_context_window_tokens",
        "pro_context_window_tokens",
    }
    float_fields = {"lite_timeout_s", "pro_timeout_s", "max_timeout_s"}
    parsed: dict[str, Any] = {}

    for token in shlex.split(args):
        key, sep, value = token.partition("=")
        if not sep:
            raise ValueError(
                "Use key=value pairs, for example: /model url=https://... "
                "pro=mimo-v2.5-pro"
            )
        normalized = aliases.get(key.strip().lower())
        if not normalized:
            raise ValueError(f"Unknown model config field: {key}")
        if normalized in context_window_fields:
            parsed[normalized] = _parse_context_window(value)
        elif normalized in integer_fields:
            parsed[normalized] = int(value)
        elif normalized in float_fields:
            parsed[normalized] = float(value)
        else:
            parsed[normalized] = value
    return parsed


def _parse_confirmation_edit_args(args: str) -> dict[str, Any]:
    field_path = ""
    new_value = ""
    unit = ""
    reason = ""
    for token in shlex.split(args):
        key, sep, value = token.partition("=")
        if not sep:
            raise ValueError(
                "Use field.path=value, optionally with unit=... and reason=..."
            )
        normalized = key.strip()
        if normalized == "unit":
            unit = value
        elif normalized == "reason":
            reason = value
        elif not field_path:
            field_path = normalized
            new_value = value
        else:
            raise ValueError(f"Unknown confirmation edit field: {normalized}")
    if not field_path:
        raise ValueError("Use field.path=value")
    edit = {
        "field_path": field_path,
        "new_value": new_value,
    }
    if unit:
        edit["unit"] = unit
    if reason:
        edit["reason"] = reason
    return {
        "user_decision": "edit",
        "edits": [edit],
        "user_notes": f"Edited {field_path}.",
    }


def _copilot_model_candidates(current_models: dict[str, str]) -> list[str]:
    candidates: list[str] = []
    for tier_name in ("pro", "lite", "max"):
        value = str(current_models.get(tier_name, "") or "").strip()
        if value and value not in candidates:
            candidates.append(value)
    for value in _COMMON_COPILOT_MODELS:
        if value not in candidates:
            candidates.append(value)
    return candidates or list(_COMMON_COPILOT_MODELS)


def _cycle_string_option(current: str, options: Sequence[str], delta: int) -> str:
    values = [str(value) for value in options if str(value)]
    if not values:
        return current
    try:
        index = values.index(current)
    except ValueError:
        return values[0 if delta >= 0 else -1]
    return values[(index + delta) % len(values)]


def _cycle_context_window(current: int, delta: int) -> int:
    try:
        value = int(current)
    except (TypeError, ValueError):
        value = 0
    values = list(_CONTEXT_WINDOW_SEQUENCE)
    try:
        index = values.index(value)
    except ValueError:
        return values[0 if delta >= 0 else -1]
    return values[(index + delta) % len(values)]


def _format_context_window(value: int) -> str:
    try:
        tokens = int(value)
    except (TypeError, ValueError):
        return "unknown"
    if tokens <= 0:
        return "unknown"
    if tokens % 1_000_000 == 0:
        return f"{tokens // 1_000_000}m"
    if tokens % 1000 == 0:
        return f"{tokens // 1000}k"
    return str(tokens)


def _context_window_option_labels() -> str:
    return " | ".join(
        _format_context_window(value) for value in _CONTEXT_WINDOW_SEQUENCE
    )


def _model_config_help_lines() -> list[str]:
    return [
        "Model",
        "set: /model url=<base_url> key=<api_key> lite=<model> pro=<model> max=<model>",
        "tune: /model lite_tokens=<n> pro_tokens=<n> max_tokens=<n>",
        "ctx: /model lite_window=100k pro_window=500k max_window=1m",
        "time: /model lite_timeout=<s> pro_timeout=<s> max_timeout=<s>",
    ]


def _is_confirmation_approval_text(text: str) -> bool:
    return text.strip().lower() in _CONFIRMATION_APPROVAL_TEXTS


def _tui_run_briefing_context(query: str) -> dict[str, Any]:
    return {
        "status": "approved",
        "understanding": "TUI run command was explicitly submitted.",
        "final_query": query,
        "approval_request": {
            "requires_human_approval": True,
            "summary": "Approved from RadAgent TUI.",
        },
    }


def _simulation_briefing_query_from_result(result: Any) -> str:
    commands = getattr(result, "commands", [])
    if not isinstance(commands, list):
        return ""
    for command in commands:
        if not isinstance(command, dict):
            continue
        if command.get("name") != "start_simulation_briefing":
            continue
        args = command.get("args")
        if not isinstance(args, dict):
            return ""
        return str(args.get("query", "")).strip()
    return ""


_CONTEXT_WINDOW_OPTIONS = {
    "100k": 100_000,
    "200k": 200_000,
    "500k": 500_000,
    "1m": 1_000_000,
}


def _parse_context_window(value: str) -> int:
    normalized = value.strip().lower().replace("_", "")
    if normalized in _CONTEXT_WINDOW_OPTIONS:
        return _CONTEXT_WINDOW_OPTIONS[normalized]
    if normalized.endswith("k"):
        number = normalized[:-1]
        if number.isdigit() and int(number) > 0:
            return int(number) * 1000
    if normalized.isdigit() and int(normalized) > 0:
        return int(normalized) * 1000
    raise ValueError("Context window must use k units, for example: 100k, 200k, 750k, 1m")


def _briefing_value(value: Any, key: str, default: Any = "") -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _load_textual() -> _TextualModules:
    try:
        from textual import containers, widgets
        from textual.app import App, ComposeResult
        from textual.binding import Binding
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            raise TextualNotInstalledError from exc
        raise
    return _TextualModules(
        app=App,
        binding=Binding,
        compose_result=ComposeResult,
        containers=containers,
        widgets=widgets,
    )
