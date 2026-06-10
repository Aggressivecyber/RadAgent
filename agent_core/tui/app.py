from __future__ import annotations

import shlex
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from agent_core.app import RadAgentAppService
from agent_core.tui.adapters import (
    event_to_row,
    render_header,
    render_markdown_row,
    render_row,
    row_css_class,
    status_to_header,
)
from agent_core.tui.commands import CommandParseError, parse_command
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
        screen_bg="#0b0f14",
        surface_bg="#0f151c",
        row_bg="#141c25",
        composer_bg="#111923",
        header_bg="#d6b56d",
        header_fg="#11161d",
        border="#253342",
        focus="#d6b56d",
        text="#d8dee9",
        muted="#78889a",
        success="#a6d189",
        running="#6fb6ff",
        warning="#f0c674",
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

        #timeline {{
            height: 1fr;
            padding: 1 2 0 2;
            border: solid {theme.border};
            background: {theme.surface_bg};
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
            color: {theme.text};
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
            height: 3;
            padding: 0 2;
            background: {theme.screen_bg};
            border-top: solid {theme.border};
        }}

        #prompt {{
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
        }}

        #inspector.visible {{
            display: block;
        }}
    """


def create_app_class(*, theme: str = "radagent") -> type[Any]:
    """Create the Textual app class after optional dependencies are available."""
    textual = _load_textual()
    textual_app = textual.app
    horizontal = textual.containers.Horizontal
    vertical_scroll = textual.containers.VerticalScroll
    input_widget = textual.widgets.Input
    markdown = textual.widgets.Markdown
    static = textual.widgets.Static
    css = _css_for_theme(_THEMES[theme])

    class RadAgentTUI(textual_app):  # type: ignore[misc, valid-type]
        """Terminal-native RadAgent workbench."""

        TITLE = "RadAgent"
        CSS = css
        BINDINGS = [
            ("ctrl+l", "focus_composer", "Input"),
            ("ctrl+p", "show_jobs", "Jobs"),
            ("ctrl+i", "toggle_inspector", "Inspect"),
            ("ctrl+o", "show_artifacts", "Artifacts"),
            ("escape", "close_inspector", "Close"),
            ("f1", "show_help", "Help"),
            ("ctrl+c", "interrupt_or_quit", "Stop"),
        ]

        def __init__(
            self,
            *,
            service: RadAgentAppService | None = None,
            execution_mode: str = "strict",
        ) -> None:
            super().__init__()
            self.service = service or RadAgentAppService(execution_mode=execution_mode)
            self._busy = False
            self._operation_worker: Any = None
            self._rows: list[TimelineRow] = []

        def compose(self) -> Any:
            yield static("", id="header")
            yield vertical_scroll(id="timeline")
            with horizontal(id="composer"):
                yield input_widget(
                    placeholder="Ask RadAgent, or run: /run <simulation request>",
                    id="prompt",
                )
            yield static(
                "Ctrl+L input  Ctrl+P jobs  Ctrl+I inspect  Ctrl+O artifacts  F1 help  Ctrl+C stop",
                id="footer",
            )
            yield static("", id="inspector")

        def on_mount(self) -> None:
            self._refresh_header()
            self._add_system_row("RadAgent TUI ready", "Type a message or /run <request>.")
            self.run_worker(self._listen_events(), name="radagent-events", exclusive=False)
            self.action_focus_composer()

        async def _listen_events(self) -> None:
            async for event in self.service.subscribe_events():
                self._add_event_row(event)
                self._refresh_header()

        async def on_input_submitted(self, event: Any) -> None:
            text = event.value.strip()
            event.input.value = ""
            await self._dispatch_text(text)

        async def _dispatch_text(self, text: str) -> None:
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
                case "logs":
                    self._show_logs()
                case "projects":
                    self._show_projects()
                case "project":
                    self._switch_project(command.args)
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

        def _start_operation(self, operation: Any) -> None:
            if self._busy:
                operation.close()
                self._add_system_row("Busy", "Wait for the current operation to finish.", "warning")
                return
            self._busy = True
            self._refresh_header()
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

        def _add_event_row(self, event: Any) -> None:
            self._append_row(event_to_row(event))

        def _add_system_row(
            self,
            title: str,
            summary: str = "",
            status: str = "info",
        ) -> None:
            row = TimelineRow(
                id=f"system:{len(self._rows)}",
                kind="system",
                status=status,
                title=title,
                summary=summary,
            )
            self._append_row(row)

        def _append_row(self, row: TimelineRow) -> None:
            self._rows.append(row)
            timeline = self.query_one("#timeline", vertical_scroll)
            if row.kind == "assistant_message" and row.summary:
                widget = markdown(
                    render_markdown_row(row),
                    classes=row_css_class(row),
                )
            else:
                widget = static(render_row(row), classes=row_css_class(row))
            timeline.mount(widget)
            scroll_end = getattr(timeline, "scroll_end", None)
            if callable(scroll_end):
                scroll_end(animate=False)

        def _refresh_header(self) -> None:
            try:
                project = str(self.service.current_project().get("slug", "default"))
            except Exception:
                project = "default"
            header = status_to_header(self.service.get_status(), project=project)
            busy = "  busy" if self._busy else ""
            self.query_one("#header", static).update(render_header(header) + busy)

        def _show_panel(self, title: str, lines: list[str]) -> None:
            body = "\n".join([title, "", *lines])
            inspector = self.query_one("#inspector", static)
            inspector.update(body)
            inspector.add_class("visible")

        def _show_jobs(self) -> None:
            jobs = self.service.list_jobs(include_all_projects=True)
            if not jobs:
                self._show_panel("Jobs", ["No jobs found."])
                return
            lines = [
                f"{job.get('status', 'unknown'):10} {job.get('job_id', '')}"
                for job in jobs[:30]
            ]
            self._show_panel("Jobs", lines)

        def _show_artifacts(self) -> None:
            artifacts = self.service.list_artifacts()
            if not artifacts:
                self._show_panel("Artifacts", ["No artifacts for the active job."])
                return
            lines = [f"{item.kind or item.stage:18} {item.path}" for item in artifacts[:30]]
            self._show_panel("Artifacts", lines)

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
                            f"thinking: {thinking}"
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
            self._show_panel("Status", lines)

        def _show_help(self) -> None:
            self._show_panel(
                "Commands",
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
                    "/projects",
                    "/project <slug-or-id>",
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
                inspector.remove_class("visible")
            else:
                self._show_status()

        def action_close_inspector(self) -> None:
            self.query_one("#inspector", static).remove_class("visible")

        def action_show_help(self) -> None:
            self._show_help()

        def action_interrupt_or_quit(self) -> None:
            if self._operation_worker is not None:
                self._operation_worker.cancel()
                self._operation_worker = None
                self._busy = False
                self._add_system_row("Interrupted", "Current operation was cancelled.", "warning")
                self._refresh_header()
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
        "lite_timeout": "lite_timeout_s",
        "pro_timeout": "pro_timeout_s",
        "max_timeout": "max_timeout_s",
    }
    integer_fields = {"lite_max_tokens", "pro_max_tokens", "max_max_tokens"}
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
        if normalized in integer_fields:
            parsed[normalized] = int(value)
        elif normalized in float_fields:
            parsed[normalized] = float(value)
        else:
            parsed[normalized] = value
    return parsed


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
