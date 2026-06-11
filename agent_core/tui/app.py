from __future__ import annotations

import inspect
import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from agent_core.app import JobStatus, RadAgentAppService
from agent_core.tui.adapters import (
    event_to_row,
    render_header,
    render_markdown_row,
    render_row,
    render_startup_status,
    render_task_context,
    row_css_class,
    status_to_header,
)
from agent_core.tui.commands import CommandParseError, parse_command
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
    compose_result: Any
    containers: Any
    widgets: Any


_THEMES: dict[str, _Theme] = {
    "radagent": _Theme(
        screen_bg="#120f14",
        surface_bg="#1a1620",
        row_bg="#241c2b",
        composer_bg="#211924",
        header_bg="#c986a8",
        header_fg="#140f14",
        border="#8d6aa3",
        focus="#c58a55",
        text="#eee4ec",
        muted="#a896ad",
        success="#d39abc",
        running="#ad8fc8",
        warning="#c58a55",
        error="#ff8a9a",
    ),
    "slate": _Theme(
        screen_bg="#090d10",
        surface_bg="#10171b",
        row_bg="#162126",
        composer_bg="#121a1f",
        header_bg="#86c5b7",
        header_fg="#08100f",
        border="#2c3c43",
        focus="#86c5b7",
        text="#dce5e4",
        muted="#80949a",
        success="#9bd49a",
        running="#8ab7ff",
        warning="#e5c07b",
        error="#ef8f8f",
    ),
    "mono": _Theme(
        screen_bg="#0c0c0c",
        surface_bg="#121212",
        row_bg="#1a1a1a",
        composer_bg="#161616",
        header_bg="#e6e6e6",
        header_fg="#111111",
        border="#3a3a3a",
        focus="#ffffff",
        text="#e2e2e2",
        muted="#8a8a8a",
        success="#cfcfcf",
        running="#f0f0f0",
        warning="#dddddd",
        error="#ffffff",
    ),
}
_THEME_NAMES = tuple(_THEMES)
_OPTION_ROWS = ("language", "theme")


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point for the Textual RadAgent TUI."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(_usage())
        return 0
    execution_mode = "strict"
    theme_name = "radagent"
    try:
        execution_mode = _option_value(argv, "--mode", execution_mode)
        theme_name = _option_value(argv, "--theme", theme_name)
    except ValueError:
        print(_usage(), file=sys.stderr)
        return 2
    if execution_mode not in {"strict", "test", "acceptance", "production"}:
        print(_usage(), file=sys.stderr)
        return 2
    if theme_name not in _THEMES:
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
        "[--theme radagent|slate|mono]"
    )


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
            border: heavy {theme.border};
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
            border: heavy {theme.border};
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
            border: heavy {theme.border};
        }}

        #prompt:focus {{
            border: heavy {theme.focus};
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
            border: heavy {theme.focus};
            background: {theme.composer_bg};
            color: {theme.text};
            display: none;
            text-style: bold;
        }}

        #inspector.visible {{
            display: block;
        }}
    """


def create_app_class(*, theme: str = "radagent") -> type[Any]:
    """Create the Textual app class after optional dependencies are available."""
    from textual.binding import Binding

    textual = _load_textual()
    textual_app = textual.app
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
            Binding("ctrl+l", "focus_composer", "Input"),
            Binding("ctrl+p", "show_options", "Options"),
            Binding("ctrl+i", "toggle_inspector", "Inspect"),
            Binding("ctrl+t", "show_trace", "Trace"),
            Binding("ctrl+o", "show_artifacts", "Artifacts"),
            Binding("up", "options_previous", show=False, priority=True),
            Binding("down", "options_next", show=False, priority=True),
            Binding("left", "options_decrement", show=False, priority=True),
            Binding("right", "options_increment", show=False, priority=True),
            Binding("enter", "options_apply", show=False, priority=True),
            Binding("escape", "close_inspector", "Close"),
            Binding("f1", "show_help", "Help"),
            Binding("ctrl+c", "interrupt_or_quit", "Stop"),
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
            self._rows: list[TimelineRow] = []
            self._row_widgets: dict[str, Any] = {}
            self._trace_snippets: list[str] = []
            self._language = DEFAULT_LANGUAGE
            self._theme_name = theme
            self._options_open = False
            self._options_selected = 0
            self._options_draft_language = self._language
            self._options_draft_theme = self._theme_name

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
            self.action_focus_composer()

        async def _listen_events(self) -> None:
            async for event in self.service.subscribe_events():
                self._add_event_row(event)
                self._refresh_header()
                self._refresh_task_context()

        async def on_input_submitted(self, event: Any) -> None:
            text = event.value.strip()
            event.input.value = ""
            await self._dispatch_text(text)

        async def _dispatch_text(self, text: str) -> None:
            if not text.startswith("/") and text != "?":
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
                case "run":
                    self._start_operation(
                        self.service.start_job(
                            command.args,
                            run_mode=self.service.execution_mode,
                            auto_continue=True,
                        )
                    )
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
                case "artifacts":
                    self._show_artifacts()
                case "artifact":
                    self._show_artifact(command.args)
                case "gates":
                    self._show_gates()
                case "memory":
                    self._show_memory()
                case "confirm":
                    self._show_confirmation()
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
                case "inspect":
                    self._show_status()
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
                    "Copliot busy",
                    (
                        "Copliot is still responding. Commands such as /options "
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
                self._add_system_row("Copliot failed", str(exc), "error")
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
                await operation
            except Exception as exc:
                self._add_system_row("Operation failed", str(exc), "error")
            finally:
                self._busy = False
                self._operation_worker = None
                self._refresh_header()
                self._refresh_task_context()

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
                title="Copliot",
                summary=self._t("thinking.analyzing"),
            )
            self._append_row(row)
            return row.id

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
            self.query_one("#footer", static).update(label("footer", self._language))
            prompt = self.query_one("#prompt", input_widget)
            prompt.placeholder = label("prompt.placeholder", self._language)

        def _refresh_task_context(self) -> None:
            status = self._status_with_controller_usage()
            self.query_one("#task-context", static).update(
                render_task_context(status, language=self._language)
            )

        def _status_with_controller_usage(self) -> JobStatus:
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
            if not jobs:
                self._show_panel(self._t("jobs.title"), [self._t("jobs.empty")])
                return
            lines = [
                f"{job.get('status', 'unknown'):10} {job.get('job_id', '')}"
                for job in jobs[:30]
            ]
            self._show_panel(self._t("jobs.title"), lines)

        def _show_artifacts(self) -> None:
            artifacts = self.service.list_artifacts()
            if not artifacts:
                self._show_panel(self._t("artifacts.title"), [self._t("artifacts.empty")])
                return
            lines = [f"{item.kind or item.stage:18} {item.path}" for item in artifacts[:30]]
            self._show_panel(self._t("artifacts.title"), lines)

        def _show_artifact(self, path: str) -> None:
            artifact = self.service.read_artifact(path, max_chars=8000)
            if not artifact.exists:
                self._show_panel("Artifact", [f"Missing: {path}"])
                return
            if artifact.kind == "binary":
                self._show_panel(
                    "Artifact",
                    [f"Binary file: {artifact.path}", f"{artifact.size_bytes} bytes"],
                )
                return
            content = artifact.text
            if artifact.truncated:
                content += "\n\n[truncated]"
            self._show_panel("Artifact", content.splitlines()[:200])

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
            if not review.get("report_path"):
                self._show_panel("Confirmation", ["No confirmation report for the active job."])
                return
            preview = str(review.get("preview", ""))
            lines = [
                f"status: {review.get('status', '') or 'unknown'}",
                f"unconfirmed: {review.get('unconfirmed_assumptions_count', 0)}",
                f"report: {review.get('report_path', '')}",
                "",
                *preview.splitlines()[:180],
            ]
            self._show_panel("Confirmation", lines)

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
            if normalized in _THEMES:
                self._apply_theme(normalized)
                return
            self._language = parse_language(value)
            self._refresh_footer()
            self._refresh_task_context()

        def _open_options(self) -> None:
            self._options_open = True
            self._options_selected = 0
            self._options_draft_language = self._language
            self._options_draft_theme = self._theme_name
            self.refresh_bindings()
            self._render_options_panel()

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
                "",
                self._t("options.controls"),
                self._t("options.context_window"),
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
                    "/resume <job_id>",
                    "/artifacts",
                    "/artifact <path>",
                    "/gates",
                    "/memory",
                    "/confirm",
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
                self._show_status()

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

        def action_options_previous(self) -> None:
            self._change_option_selection(-1)

        def action_options_next(self) -> None:
            self._change_option_selection(1)

        def action_options_decrement(self) -> None:
            self._change_option_value(-1)

        def action_options_increment(self) -> None:
            self._change_option_value(1)

        def action_options_apply(self) -> None:
            self._apply_options_draft()

        def action_show_trace(self) -> None:
            self._show_trace()

        def action_interrupt_or_quit(self) -> None:
            if self._controller_worker is not None:
                self._controller_worker.cancel()
                self._controller_worker = None
                self._finish_thinking_row(
                    self._controller_thinking_id,
                    status="warning",
                    summary="Copliot response was cancelled.",
                )
                self._controller_thinking_id = ""
                self._add_system_row("Interrupted", "Copliot response was cancelled.", "warning")
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
    except ModuleNotFoundError as exc:
        if exc.name == "textual":
            raise TextualNotInstalledError from exc
        raise
    return _TextualModules(
        app=App,
        compose_result=ComposeResult,
        containers=containers,
        widgets=widgets,
    )
