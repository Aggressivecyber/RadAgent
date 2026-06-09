"""RadAgent interactive terminal REPL.

Provides an interactive, step-by-step interface for running the RadAgent
pipeline.  Unlike the one-shot CLI (``python -m agent_core.main "query"``),
the REPL lets users pause at human-confirmation points, inspect generated
code, trigger Geant4 builds manually, and run simulations with custom event
counts.

Start with::

    python -m agent_core.main -i

Slash commands
--------------
/run <query>   Execute pipeline through codegen with a new query.
/step          Execute the next pipeline phase.
/status        Show current pipeline state and completed phases.
/model         Display the current G4 Model IR (rich table).
/confirm       Interactively confirm AI assumptions.
/code          List and preview generated C++ files.
/build         Run cmake configure + make.
/sim [events]  Run the Geant4 simulation (default 1000 events).
/results       Show simulation output summary.
/gates         Show gate-check results.
/jobs          List existing jobs.
/resume <job>  Resume a persisted job snapshot.
/projects      List projects.
/project ...   Create or switch projects.
/help          Show help text.
/quit          Exit REPL.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

logger = logging.getLogger(__name__)

# ── Pipeline phases in execution order ──────────────────────────────────

_PIPELINE_PHASES: list[str] = [
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
]

# Phases that run automatically (no human interaction needed)
_AUTO_PHASES: set[str] = {
    "prepare_workspace",
    "context",
    "task_planning",
    "g4_modeling",
    "g4_codegen",
    "patch",
    "gate",
    "artifact",
    "report",
}

# Phases that block for human input
_INTERACTIVE_PHASES: set[str] = {"human_confirmation"}


class _QuitREPLError(Exception):
    """Signal to exit the REPL loop."""


def _load_json_safe(path: Path) -> dict[str, Any] | list[Any] | None:
    """Load JSON from a file with error handling."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Corrupted JSON file %s: %s", path, exc)
        return None


class RadAgentREPL:
    """Interactive terminal REPL for RadAgent.

    Drives the pipeline **one phase at a time**, pausing at
    ``human_confirmation`` for interactive review.  Uses Rich for
    colourised output and prompt_toolkit for history / completion.
    """

    _VALID_MODES: frozenset[str] = frozenset(
        {"strict", "test", "acceptance", "production"}
    )

    def __init__(self, execution_mode: str = "strict") -> None:
        if execution_mode not in self._VALID_MODES:
            raise ValueError(f"Invalid execution_mode: {execution_mode}")
        self.console = Console()
        self.execution_mode: str = execution_mode
        self.state: dict[str, Any] = {}
        self.current_phase_idx: int = 0
        self._completed_phases: list[str] = []
        self._subgraph_nodes: dict[str, Any] | None = None
        self._chat_agent: Any = None  # lazy-initialized ChatAgent
        self._store: Any = None  # lazy-initialized RadAgentStore
        # Persistent command history across inputs
        self._history: Any = None
        try:
            from prompt_toolkit.history import InMemoryHistory

            self._history = InMemoryHistory()
        except ImportError:
            pass

        # Tool call logging — track calls per phase
        self._phase_start_time: float = 0.0
        self._setup_tool_logger()

    def _setup_tool_logger(self) -> None:
        """Initialize tool call logging."""
        import time

        from agent_core.models.tool_logger import get_tool_logger

        tool_logger = get_tool_logger()

        # Set up log file in workspace
        log_dir = Path("repair_logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        tool_logger.set_log_file(log_dir / "tool_calls.jsonl")

        self._phase_start_time = time.time()

    def _on_tool_call(self, record: Any) -> None:
        """Callback for tool call events — displays in REPL."""
        task = record.task
        provider = record.provider
        model = record.model_name
        latency = record.latency_ms
        success = "✓" if record.success else "✗"
        style = "green" if record.success else "red"

        # Format latency
        if latency > 1000:
            latency_str = f"{latency / 1000:.1f}s"
        else:
            latency_str = f"{latency:.0f}ms"

        # Format metadata
        meta = record.metadata
        meta_str = ""
        if meta.get("module_name"):
            meta_str = f" [{meta['module_name']}]"

        self.console.print(
            f"    [dim]🔧 {task}{meta_str}[/dim] "
            f"[{style}]{success}[/{style}] "
            f"[dim]{provider}/{model} ({latency_str})[/dim]"
        )

    # ── Lazy-loaded subgraph nodes ──────────────────────────────────

    def _get_subgraph_nodes(self) -> dict[str, Any]:
        if self._subgraph_nodes is None:
            from agent_core.graph.main_graph import build_subgraph_nodes

            self._subgraph_nodes = build_subgraph_nodes()
        return self._subgraph_nodes

    def _get_chat_agent(self):
        """Lazy-initialize the conversational chat agent."""
        if self._chat_agent is None:
            from agent_core.chat.agent import ChatAgent

            self._chat_agent = ChatAgent()
        return self._chat_agent

    def _get_store(self):
        """Lazy-initialize workspace metadata storage."""
        if self._store is None:
            from agent_core.storage import RadAgentStore

            self._store = RadAgentStore()
        return self._store

    # ── Main loop ───────────────────────────────────────────────────

    async def run(self) -> None:
        """Run the interactive REPL loop."""
        self.console.print(
            Panel(
                "[bold green]RadAgent Interactive REPL[/bold green]\n"
                "Type a simulation request or /help for commands.",
                title="RadAgent",
                border_style="green",
            )
        )

        while True:
            try:
                text = await asyncio.to_thread(self._read_input)
            except (EOFError, KeyboardInterrupt):
                self.console.print("\n[dim]Goodbye.[/dim]")
                break

            text = text.strip()
            if not text:
                continue

            try:
                await self.handle_input(text)
            except _QuitREPLError:
                self.console.print("[dim]Goodbye.[/dim]")
                break
            except Exception as exc:
                self.console.print(f"[bold red]Error:[/bold red] {exc}")
                logger.exception("REPL command error")

    def _read_input(self) -> str:
        """Read a line from stdin (runs in a thread for async compat)."""
        job_id = self.state.get("job_id", "")
        # Show short job ID in prompt (truncate long title slugs)
        if job_id:
            short = job_id if len(job_id) <= 32 else job_id[:29] + "..."
            prompt_text = f"RadAgent[{short}]> "
        else:
            prompt_text = "RadAgent> "

        try:
            from prompt_toolkit import prompt as pt_prompt

            return pt_prompt(prompt_text, history=self._history)
        except ImportError:
            return input(prompt_text)

    # ── Input dispatch ──────────────────────────────────────────────

    async def handle_input(self, text: str) -> None:
        """Dispatch input: slash command or natural-language query.

        Natural language input goes through the LLM Intent Router first.
        Only simulation_work intents are treated as /run.
        """
        text = text.strip()
        if not text:
            return
        if text.startswith("/"):
            parts = text.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1] if len(parts) > 1 else ""
            await self._dispatch_command(cmd, arg)
        else:
            # Natural language → classify intent first
            await self._handle_natural_language(text)

    async def _handle_natural_language(self, text: str) -> None:
        """Handle natural language input via LLM Intent Router."""
        from agent_core.intent.router import classify_intent_with_lite_model

        has_active_job = bool(self.state.get("job_id"))

        self.console.print("  [dim]Classifying intent...[/dim]", end=" ")

        intent_result = await classify_intent_with_lite_model(
            text,
            has_active_job=has_active_job,
        )

        detail = f":{intent_result.intent_detail}" if intent_result.intent_detail else ""
        self.console.print(f"[dim]{intent_result.intent}{detail}[/dim]")

        if intent_result.intent == "chat":
            await self._chat_reply(text)
            return

        if intent_result.intent == "simulation_work":
            if intent_result.intent_detail == "human_confirmation_response":
                # Check if there's a pending confirmation
                if self.state.get("confirmation_request_path"):
                    await self.cmd_confirm()
                else:
                    self.console.print("[yellow]当前没有待确认的方案。[/yellow]")
                return
            await self.cmd_run(text)
            return

        if intent_result.intent_detail == "human_confirmation_response":
            if self.state.get("confirmation_request_path"):
                await self.cmd_confirm()
            else:
                self.console.print("[yellow]当前没有待确认的方案。[/yellow]")
            return

        await self._chat_reply(text)

    async def _chat_reply(self, text: str) -> None:
        """Send text to the chat agent and display the response."""
        agent = self._get_chat_agent()
        with self.console.status("[dim]思考中...[/dim]"):
            response = await agent.chat(text)
        self.console.print(f"\n[green]{response}[/green]\n")

    async def _dispatch_command(self, cmd: str, arg: str) -> None:
        """Route slash commands to handler methods."""
        handlers: dict[str, Any] = {
            "/run": lambda: self.cmd_run(arg),
            "/step": lambda: self.cmd_step(),
            "/status": lambda: self.cmd_status(),
            "/model": lambda: self.cmd_model(),
            "/confirm": lambda: self.cmd_confirm(),
            "/code": lambda: self.cmd_code(),
            "/build": lambda: self.cmd_build(),
            "/sim": lambda: self.cmd_run_sim(arg),
            "/results": lambda: self.cmd_results(),
            "/gates": lambda: self.cmd_gates(),
            "/jobs": lambda: self.cmd_jobs(),
            "/resume": lambda: self.cmd_resume(arg),
            "/projects": lambda: self.cmd_projects(),
            "/project": lambda: self.cmd_project(arg),
            "/tools": lambda: self.cmd_tools(),
            "/chat": lambda: self.cmd_chat(arg),
            "/help": lambda: self.cmd_help(),
            "/quit": self._cmd_quit,
        }
        handler = handlers.get(cmd)
        if handler is None:
            self.console.print(f"[yellow]Unknown command:[/yellow] {cmd}")
            self.console.print("Type /help for available commands.")
            return
        result = handler()
        if asyncio.iscoroutine(result):
            await result

    # ── Pipeline commands ───────────────────────────────────────────

    async def cmd_run(self, query: str) -> None:
        """Execute pipeline from scratch through codegen with *query*."""
        if not query:
            self.console.print("[yellow]Usage:[/yellow] /run <query>")
            return

        # Reset state
        self.state = {
            "user_query": query,
            "job_id": "",
            "errors": [],
            "retry_count": 0,
            "max_retries_reached": False,
            "execution_mode": self.execution_mode,
            "skipped_gates": [],
        }
        self.current_phase_idx = 0
        self._completed_phases = []

        # Reset chat history for new job
        if self._chat_agent is not None:
            self._chat_agent.reset()

        # Phase 0: prepare_workspace
        await self._run_phase("prepare_workspace")

        # Auto phases: context → task_planning → g4_modeling
        for phase in ["context", "task_planning", "g4_modeling"]:
            if not await self._run_phase(phase):
                return

        # Check if human confirmation is needed
        if self.state.get("human_confirmation_required"):
            n_assumptions = self.state.get("unconfirmed_assumptions_count", "?")
            self.console.print(
                "\n[bold yellow]⚠ Human confirmation required[/bold yellow]"
                f" — {n_assumptions} assumptions need review"
            )
            self.console.print(
                "  [dim]Use /confirm to review assumptions, then /step to continue.[/dim]\n"
            )
            self.current_phase_idx = _PIPELINE_PHASES.index("human_confirmation")
            return

        # Continue: codegen → patch → gate → artifact → report
        await self._auto_remaining()

    async def cmd_chat(self, message: str) -> None:
        """Chat with the AI assistant. Usage: /chat [message] or /chat reset."""
        if message.strip() == "reset":
            if self._chat_agent is not None:
                self._chat_agent.reset()
            self.console.print("[dim]对话历史已清空。[/dim]")
            return
        if message.strip():
            await self._chat_reply(message.strip())
        else:
            self.console.print(
                "[dim]用法: /chat <消息> — 与 AI 对话\n      /chat reset — 清空对话历史[/dim]"
            )

    async def cmd_step(self) -> None:
        """Execute the next single pipeline phase."""
        if not self.state:
            self.console.print("[yellow]No active pipeline.[/yellow] Start with /run <query>")
            return

        if self.current_phase_idx >= len(_PIPELINE_PHASES):
            self.console.print("[green]Pipeline complete.[/green]")
            return

        phase = _PIPELINE_PHASES[self.current_phase_idx]

        if phase == "human_confirmation" and not self.state.get("raw_human_response"):
            self.console.print("[yellow]Human confirmation pending.[/yellow] Run /confirm first.")
            return

        success = await self._run_phase(phase)
        if success and self.current_phase_idx < len(_PIPELINE_PHASES):
            next_phase = _PIPELINE_PHASES[self.current_phase_idx]
            self.console.print(f"  [dim]Next: {next_phase}. Use /step to continue.[/dim]")

    async def cmd_status(self) -> None:
        """Display current pipeline state."""
        if not self.state:
            self.console.print("[dim]No active pipeline.[/dim]")
            return

        job_id = self.state.get("job_id", "N/A")
        query = self.state.get("user_query", "N/A")

        table = Table(title=f"Pipeline Status — {job_id}")
        table.add_column("Phase", style="cyan")
        table.add_column("Status", style="green")

        for phase in _PIPELINE_PHASES:
            if phase in self._completed_phases:
                table.add_row(phase, "✓ done")
            elif (
                self.current_phase_idx < len(_PIPELINE_PHASES)
                and _PIPELINE_PHASES[self.current_phase_idx] == phase
            ):
                table.add_row(phase, "⏸ current")
            else:
                table.add_row(phase, "· pending")

        self.console.print(table)
        self.console.print(f"  Query: {query}")
        self.console.print(f"  Mode: {self.execution_mode}")

        for key in [
            "g4_modeling_status",
            "g4_codegen_status",
            "validation_status",
            "confirmation_status",
        ]:
            val = self.state.get(key)
            if val:
                self.console.print(f"  {key}: {val}")

    async def cmd_model(self) -> None:
        """Display the current G4 Model IR."""
        ir_path = self.state.get("g4_model_ir_path")
        if not ir_path or not Path(ir_path).exists():
            self.console.print("[yellow]No model IR available.[/yellow] Run /run first.")
            return

        model_ir = _load_json_safe(Path(ir_path))
        if model_ir is None:
            self.console.print(f"[red]Corrupted model IR file:[/red] {ir_path}")
            return
        self._render_model_summary(model_ir)

    async def cmd_confirm(self) -> None:
        """Interactively confirm AI assumptions and auto-continue to codegen."""
        # ── Step 1: Show construction report (model IR summary) ────────
        ir_path = self.state.get("g4_model_ir_path")
        if ir_path and Path(ir_path).exists():
            model_ir = _load_json_safe(Path(ir_path))
            if model_ir:
                self.console.print("\n[bold cyan]═══ 施工方案报告 ═══[/bold cyan]")
                self._render_model_summary(model_ir)
                self.console.print("")

        # ── Step 2: Build confirmation request if needed ───────────────
        request_path = self.state.get("confirmation_request_path")
        if not request_path or not Path(request_path).exists():
            self.console.print("  [dim]Building confirmation request...[/dim]")
            # stop_at_interrupt: subgraph returns pending at human_interrupt,
            # but confirmation_request_path is already set by generate_confirmation_request
            await self._run_phase("human_confirmation", stop_at_interrupt=True)
            request_path = self.state.get("confirmation_request_path")

        if not request_path or not Path(request_path).exists():
            self.console.print("[yellow]No confirmation request available.[/yellow]")
            return

        request_data = _load_json_safe(Path(request_path))
        if request_data is None:
            self.console.print(f"[red]Corrupted confirmation request:[/red] {request_path}")
            return

        # ── Step 3: Show summary from confirmation request ─────────────
        summary = request_data.get("summary_for_user", "")
        if summary:
            self.console.print(Panel(summary, title="方案摘要", border_style="cyan"))

        questions = request_data.get("questions", [])

        # ── Step 4: Handle questions or ask for approval ───────────────
        edits: list[dict[str, Any]] = []
        all_approved = True

        if not questions:
            self.console.print("[green]✓ 所有参数已确认，无需额外假设。[/green]")
            self.console.print("\n[bold yellow]请确认施工方案：[/bold yellow]")
            answer = await asyncio.to_thread(
                self._prompt_choice,
                "[a]pprove 批准 / [r]eject 拒绝?",
                ("a", "r"),
                "a",
            )
            if answer == "a":
                self.state["raw_human_response"] = {
                    "user_decision": "approve",
                    "edits": [],
                    "user_notes": "User approved (no questions)",
                }
            else:
                self.state["raw_human_response"] = {
                    "user_decision": "reject",
                    "edits": [],
                    "user_notes": "User rejected",
                }
                self.console.print("  [red]✗ 已拒绝[/red]")
                return
        else:
            # Interactive Q&A
            for i, q in enumerate(questions, 1):
                field = q.get("field_path", q.get("field", "unknown"))
                current = q.get("current_value", q.get("value", "?"))
                reason = q.get("reason", "")
                confidence = q.get("confidence", 0)

                self.console.print(
                    Panel(
                        f"Field: [cyan]{field}[/cyan]\n"
                        f"Current: [bold]{current}[/bold]\n"
                        f"Reason: {reason}\n"
                        f"Confidence: {confidence:.0%}",
                        title=f"Assumption {i}/{len(questions)}",
                        border_style="yellow",
                    )
                )

                answer = await asyncio.to_thread(
                    self._prompt_choice,
                    "[a]pprove / [e]dit / [r]eject?",
                    ("a", "e", "r"),
                    "a",
                )

                if answer == "e":
                    new_val = await asyncio.to_thread(
                        self._prompt_text, f"  New value for {field}: "
                    )
                    edits.append(
                        {
                            "field_path": field,
                            "new_value": new_val,
                            "reason": "User edit in REPL",
                        }
                    )
                    all_approved = False
                    self.console.print(f"  [green]✓ Edited:[/green] {field} → {new_val}")
                elif answer == "r":
                    edits.append(
                        {
                            "field_path": field,
                            "new_value": None,
                            "reason": "User rejected in REPL",
                        }
                    )
                    all_approved = False
                    self.console.print(f"  [red]✗ Rejected:[/red] {field}")
                else:
                    self.console.print(f"  [green]✓ Approved:[/green] {field}")

            decision = "approve" if all_approved else "edit"
            self.state["raw_human_response"] = {
                "schema_version": "confirmation_response_v1",
                "job_id": self.state.get("job_id", ""),
                "round_id": request_data.get("round_id", 1),
                "user_decision": decision,
                "edits": edits,
                "user_notes": f"Interactive REPL confirmation ({decision})",
            }

        # ── Step 5: Run human_confirmation phase to merge ──────────────
        merge_success = await self._run_phase("human_confirmation")
        if not merge_success:
            self.console.print("[red]Failed to merge confirmation.[/red]")
            return

        # ── Step 6: Show clear success and auto-continue ───────────────
        self.console.print(
            "\n"
            "[bold green]═══════════════════════════════════════════[/bold green]\n"
            "[bold green]  ✓ 施工方案已批准[/bold green]\n"
            "[bold green]  正在进入代码生成阶段...[/bold green]\n"
            "[bold green]═══════════════════════════════════════════[/bold green]\n"
        )

        # Auto-continue: codegen → patch → gate → artifact → report
        await self._auto_remaining()

    async def cmd_code(self) -> None:
        """List and preview generated C++ files."""
        code_dir = self.state.get("generated_code_dir")
        if not code_dir or not Path(code_dir).exists():
            self.console.print("[yellow]No generated code yet.[/yellow] Run /run first.")
            return

        root = Path(code_dir)
        files = sorted(p for p in root.rglob("*") if p.is_file() and not p.name.startswith("."))

        if not files:
            self.console.print("[yellow]No source files found.[/yellow]")
            return

        self.console.print(f"\n[bold]Generated code:[/bold] {code_dir}")
        for f in files:
            rel = f.relative_to(root)
            lines = f.read_text(errors="replace").count("\n") + 1
            self.console.print(f"  📄 {rel} ({lines} lines)")

        name = await asyncio.to_thread(self._prompt_text, "  View file (name or Enter to skip): ")
        if name.strip():
            target = root / name.strip()
            if target.is_file():
                content = target.read_text(errors="replace")
                self.console.print(Panel(content, title=str(target), border_style="blue"))
            else:
                self.console.print(f"  [yellow]File not found:[/yellow] {name}")

    async def cmd_build(self) -> None:
        """Run cmake configure + make for the generated Geant4 project."""
        code_dir = self.state.get("generated_code_dir")
        if not code_dir or not Path(code_dir).exists():
            self.console.print("[yellow]No generated code to build.[/yellow] Run /run first.")
            return

        from agent_core.tools.geant4_runner import Geant4Runner

        runner = Geant4Runner()
        if not runner.geant4_available:
            self.console.print("[red]Geant4 not available.[/red] Check /etc/profile.d/geant4.sh")
            return

        source_dir = str(Path(code_dir) / "05_geant4")
        if not (Path(code_dir) / "05_geant4" / "CMakeLists.txt").exists():
            source_dir = code_dir if (Path(code_dir) / "CMakeLists.txt").exists() else ""
            if not source_dir:
                self.console.print(f"[yellow]No CMakeLists.txt found in {code_dir}[/yellow]")
                return

        build_dir = str(Path(code_dir) / "build")

        self.console.print("  [dim]Running cmake configure...[/dim]")
        cfg = await runner.configure(source_dir, build_dir)
        if not cfg["success"]:
            self.console.print(f"[red]cmake failed:[/red]\n{cfg['errors']}")
            return
        self.console.print("  [green]✓ cmake configured[/green]")

        self.console.print("  [dim]Building (make -j4)...[/dim]")
        bld = await runner.build(build_dir, threads=4)
        if not bld["success"]:
            self.console.print(f"[red]make failed:[/red]\n{bld['errors']}")
            return

        exe = bld.get("executable_path", "unknown")
        self.console.print("  [green]✓ Build successful[/green]")
        self.console.print(f"  Executable: {exe}")

        # Store for /sim
        self.state["_executable_path"] = exe

    async def cmd_run_sim(self, arg: str) -> None:
        """Run the Geant4 simulation."""
        exe = self.state.get("_executable_path")
        if not exe or not Path(exe).exists():
            self.console.print("[yellow]No built executable.[/yellow] Run /build first.")
            return

        if arg.strip().isdigit():
            events = int(arg)
        else:
            events = 1000
            if arg.strip():
                self.console.print(
                    f"[yellow]Invalid event count '{arg}', defaulting to 1000.[/yellow]"
                )

        job_id = self.state.get("job_id", "repl_run")

        from agent_core.workspace.manager import WorkspaceManager

        ws = WorkspaceManager()
        output_dir = str(ws.get_job(job_id).output_dir())

        self.console.print(f"  [dim]Running {events} events...[/dim]")

        from agent_core.tools.geant4_runner import Geant4Runner

        runner = Geant4Runner()
        result = await runner.simulate(
            executable=exe,
            events=events,
            output_dir=output_dir,
            job_id=job_id,
        )

        if result["success"]:
            self.console.print("  [green]✓ Simulation complete[/green]")
            self.console.print(f"  Output: {output_dir}")
            self.state["_sim_output_dir"] = output_dir
        else:
            self.console.print(f"[red]Simulation failed:[/red]\n{result['errors']}")

    async def cmd_results(self) -> None:
        """Show simulation output summary."""
        output_dir = self.state.get("_sim_output_dir")
        if not output_dir or not Path(output_dir).exists():
            self.console.print("[yellow]No simulation results.[/yellow] Run /sim <events> first.")
            return

        root = Path(output_dir)
        files = sorted(p for p in root.rglob("*") if p.is_file())

        self.console.print(f"\n[bold]Simulation output:[/bold] {output_dir}")
        for f in files:
            rel = f.relative_to(root)
            size = f.stat().st_size
            self.console.print(f"  📊 {rel} ({size:,} bytes)")

        # Show a summary file if present
        for summary_name in ("summary.json", "dose_summary.json", "result.json"):
            summary_path = root / summary_name
            if summary_path.exists():
                data = _load_json_safe(summary_path)
                if data is not None:
                    self.console.print(
                        Panel(
                            json.dumps(data, indent=2, ensure_ascii=False)[:2000],
                            title=summary_name,
                            border_style="cyan",
                        )
                    )
                break

    async def cmd_gates(self) -> None:
        """Show gate-check results."""
        gates_path = self.state.get("gate_results_path")
        if not gates_path or not Path(gates_path).exists():
            self.console.print("[yellow]No gate results yet.[/yellow]")
            return

        gate_data = _load_json_safe(Path(gates_path))
        if gate_data is None:
            self.console.print(f"[red]Corrupted gate results:[/red] {gates_path}")
            return

        results = gate_data if isinstance(gate_data, list) else gate_data.get("results", [])

        if not results:
            self.console.print("[dim]No gate results found.[/dim]")
            return

        table = Table(title="Gate Check Results")
        table.add_column("Gate", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Status", style="green")
        table.add_column("Message", style="dim", max_width=60)

        status_styles = {
            "pass": "[green]✓ pass[/green]",
            "fail": "[red]✗ fail[/red]",
            "skip": "[yellow]○ skip[/yellow]",
            "error": "[red]⚠ error[/red]",
        }

        for g in results:
            gid = g.get("gate_id", g.get("id", "?"))
            name = g.get("name", g.get("gate_name", ""))
            status = g.get("status", "unknown")
            msg = g.get("message", "")
            styled = status_styles.get(status, status)
            table.add_row(str(gid), name, styled, msg)

        self.console.print(table)

    async def cmd_jobs(self) -> None:
        """List existing jobs."""
        store = self._get_store()
        store.import_existing_jobs()
        jobs = store.list_jobs()
        if not jobs:
            self.console.print("[dim]No jobs found.[/dim]")
            return

        current_job = self.state.get("job_id", "")
        project = store.current_project()
        self.console.print(
            f"[bold]Jobs[/bold] [dim]project={project['slug']} db={store.db_path}[/dim]"
        )
        for job in jobs:
            marker = "DONE" if job["status"] == "completed" else job["status"].upper()
            style = "green" if marker == "DONE" else "yellow"
            current = " ◀ current" if job["job_id"] == current_job else ""
            self.console.print(
                f"  [{style}][{marker}][/{style}] {job['job_id']}"
                f" [dim]{job['current_phase']}[/dim][bold cyan]{current}[/bold cyan]"
            )

    async def cmd_resume(self, job_id: str) -> None:
        """Resume the latest persisted state snapshot for a job."""
        job_id = job_id.strip()
        if not job_id:
            self.console.print("[yellow]Usage:[/yellow] /resume <job_id>")
            return

        store = self._get_store()
        snapshot = store.latest_state_snapshot(job_id)
        job = store.get_job(job_id)
        if snapshot is None:
            if job is None:
                self.console.print(f"[yellow]Job not found:[/yellow] {job_id}")
                return
            self.state = {
                "job_id": job["job_id"],
                "user_query": job["user_query"],
                "execution_mode": job["execution_mode"],
                "run_mode": job["run_mode"],
                "job_workspace": job["job_workspace"],
                "errors": [],
                "retry_count": 0,
                "max_retries_reached": False,
                "skipped_gates": [],
            }
            self.current_phase_idx = int(job["current_phase_idx"])
            self._completed_phases = _PIPELINE_PHASES[: self.current_phase_idx]
        else:
            self.state = dict(snapshot["state"])
            self.current_phase_idx = int(snapshot["current_phase_idx"])
            self._completed_phases = list(snapshot["completed_phases"])
        self.execution_mode = self.state.get("execution_mode", self.execution_mode)
        self.console.print(
            f"[green]Resumed[/green] {job_id} "
            f"[dim]phase={self.current_phase_idx}/{len(_PIPELINE_PHASES)}[/dim]"
        )

    async def cmd_projects(self) -> None:
        """List known projects."""
        store = self._get_store()
        current = store.current_project()
        projects = store.list_projects()
        for project in projects:
            marker = "*" if project["id"] == current["id"] else " "
            self.console.print(
                f" {marker} {project['slug']} [dim]{project['name']}[/dim]"
            )

    async def cmd_project(self, arg: str) -> None:
        """Create or switch projects.

        Usage:
          /project use <slug-or-id>
          /project new <name>
        """
        parts = arg.strip().split(maxsplit=1)
        if len(parts) != 2 or parts[0] not in {"use", "new"}:
            self.console.print("[yellow]Usage:[/yellow] /project use <slug> | /project new <name>")
            return

        store = self._get_store()
        action, value = parts
        if action == "new":
            project = store.create_project(value)
            store.set_current_project(str(project["id"]))
            self.console.print(f"[green]Created project[/green] {project['slug']}")
            return

        project = store.set_current_project(value)
        if project is None:
            self.console.print(f"[yellow]Project not found:[/yellow] {value}")
            return
        self.console.print(f"[green]Switched project[/green] {project['slug']}")

    async def cmd_tools(self) -> None:
        """Show tool call history and summary."""
        from agent_core.models.tool_logger import get_tool_logger

        tool_logger = get_tool_logger()
        records = tool_logger.get_records()

        if not records:
            self.console.print("[dim]No tool calls recorded yet.[/dim]")
            return

        # Summary
        summary = tool_logger.summary()
        self.console.print(
            f"\n[bold]Tool Call Summary:[/bold] "
            f"{summary['total_calls']} calls, "
            f"{summary['total_latency_ms']}ms total, "
            f"{summary['errors']} errors"
        )

        # By task
        if summary.get("by_task"):
            self.console.print("  [dim]By task:[/dim]")
            for task, count in summary["by_task"].items():
                self.console.print(f"    {task}: {count}")

        # Recent calls table
        table = Table(title="Recent Tool Calls")
        table.add_column("Task", style="cyan")
        table.add_column("Module", style="white")
        table.add_column("Provider", style="dim")
        table.add_column("Latency", style="green")
        table.add_column("Status", style="white")

        # Show last 20 calls
        for record in records[-20:]:
            task = record.task
            module = record.metadata.get("module_name", "")
            provider = f"{record.provider}/{record.model_name}"
            latency = record.latency_ms
            if latency > 1000:
                latency_str = f"{latency / 1000:.1f}s"
            else:
                latency_str = f"{latency:.0f}ms"
            status = "✓" if record.success else "✗"
            style = "green" if record.success else "red"
            table.add_row(task, module, provider, latency_str, f"[{style}]{status}[/{style}]")

        self.console.print(table)

        # Log file location
        if tool_logger._log_file:
            self.console.print(f"  [dim]Log: {tool_logger._log_file}[/dim]")

    async def cmd_help(self) -> None:
        """Show help text."""
        self.console.print(
            Panel(
                "[bold]/run <query>[/bold]   Execute pipeline with a new query\n"
                "[bold]/step[/bold]          Execute next pipeline phase\n"
                "[bold]/status[/bold]        Show current pipeline state\n"
                "[bold]/model[/bold]         Display G4 Model IR\n"
                "[bold]/confirm[/bold]       Interactively confirm AI assumptions\n"
                "[bold]/code[/bold]          List and preview generated C++ files\n"
                "[bold]/build[/bold]         Run cmake + make\n"
                "[bold]/sim [events][/bold]  Run simulation (default 1000 events)\n"
                "[bold]/results[/bold]       Show simulation output\n"
                "[bold]/tools[/bold]         Show LLM/tool call history\n"
                "[bold]/gates[/bold]         Show gate-check results\n"
                "[bold]/jobs[/bold]          List existing jobs\n"
                "[bold]/resume <job>[/bold]  Resume a persisted job\n"
                "[bold]/projects[/bold]      List projects\n"
                "[bold]/project use/new[/bold] Switch or create project\n"
                "[bold]/chat <msg>[/bold]    Chat with AI (with RAG + web + history)\n"
                "[bold]/chat reset[/bold]    Clear conversation history\n"
                "[bold]/help[/bold]          Show this help\n"
                "[bold]/quit[/bold]          Exit REPL\n"
                "\n[dim]Natural language input is classified by intent router.[/dim]\n"
                "[dim]Simulation requests → pipeline.  Chat/questions → AI assistant.[/dim]",
                title="RadAgent Commands",
                border_style="cyan",
            )
        )

    async def _cmd_quit(self) -> None:
        """Exit the REPL."""
        raise _QuitREPLError()

    # ── Phase execution ─────────────────────────────────────────────

    async def _run_phase(
        self,
        phase: str,
        *,
        stop_at_interrupt: bool = False,
    ) -> bool:
        """Execute a single pipeline phase.

        Returns True on success, False on failure or user interrupt.
        """

        from agent_core.models.tool_logger import get_tool_logger

        self.console.print(f"  [dim]Phase: {phase}...[/dim]")

        # Record tool calls before this phase
        tool_logger = get_tool_logger()
        calls_before = len(tool_logger.get_records())

        try:
            if phase == "prepare_workspace":
                result = await self._exec_prepare_workspace()
            elif phase in self._get_subgraph_nodes():
                node_fn = self._get_subgraph_nodes()[phase]
                result = await node_fn(self.state)
            else:
                self.console.print(f"  [yellow]Unknown phase: {phase}[/yellow]")
                return False
        except Exception as exc:
            self.console.print("  [red]✗ FAILED[/red]")
            self.console.print(f"  [red]{exc}[/red]")
            logger.exception("Phase %s failed", phase)
            return False

        # Show tool calls made during this phase
        calls_after = tool_logger.get_records()
        new_calls = calls_after[calls_before:]
        if new_calls:
            for call in new_calls:
                self._on_tool_call(call)
        else:
            self.console.print("  [dim]  (no LLM calls)[/dim]")

        # Merge result into state (immutable update pattern)
        if result:
            self.state = {**self.state, **result}

        self._completed_phases.append(phase)
        self.current_phase_idx = _PIPELINE_PHASES.index(phase) + 1
        self._persist_phase_state(phase)
        self.console.print(f"  [green]✓ {phase}[/green]")

        # Show job ID prominently after workspace is created
        if phase == "prepare_workspace" and self.state.get("job_id"):
            job_id = self.state["job_id"]
            job_dir = self.state.get("job_workspace", "")
            self.console.print(
                f"\n  [bold cyan]📋 Job ID:[/bold cyan] {job_id}\n  [dim]📁 {job_dir}[/dim]\n"
            )

        # Check for human-confirmation interrupt
        if (
            phase == "human_confirmation"
            and stop_at_interrupt
            and self.state.get("confirmation_status") == "pending"
        ):
            return False

        return True

    def _persist_phase_state(self, phase: str) -> None:
        """Persist REPL resume state and artifact indexes after a phase."""
        job_id = self.state.get("job_id")
        if not job_id:
            return
        try:
            store = self._get_store()
            status = "completed" if phase == "report" else "running"
            if self.state.get("confirmation_status") == "pending":
                status = "paused"
            store.save_state_snapshot(
                job_id=job_id,
                state=self.state,
                completed_phases=self._completed_phases,
                phase=phase,
                current_phase_idx=self.current_phase_idx,
                status=status,
            )
            self._record_state_artifacts(store, job_id)
        except Exception as exc:
            logger.warning("Failed to persist REPL state for %s: %s", job_id, exc)

    def _record_state_artifacts(self, store: Any, job_id: str) -> None:
        """Index path-like state values as artifact metadata."""
        for key, value in self.state.items():
            if not isinstance(value, str) or not value:
                continue
            if not (key.endswith("_path") or key.endswith("_dir")):
                continue
            path = Path(value)
            if not path.exists():
                continue
            stage = path.parent.name if path.is_file() else path.name
            store.record_artifact(job_id=job_id, path=str(path), stage=stage, kind=key)

    async def _exec_prepare_workspace(self) -> dict[str, Any]:
        """Create job directory structure via WorkspaceManager."""
        from agent_core.naming import build_job_id
        from agent_core.workspace.manager import WorkspaceManager

        job_id = await build_job_id(
            self.state.get("job_id", ""),
            self.state.get("user_query", ""),
        )

        ws = WorkspaceManager()
        job = ws.create_job(job_id)

        # Write user query to input stage
        job.write_text(
            "00_input",
            "user_query.md",
            f"# User Query\n\n{self.state.get('user_query', '')}\n",
        )

        # Determine execution_mode from run_mode.
        run_mode = self.state.get("run_mode", "strict")
        execution_mode_map = {
            "strict": "strict",
            "test": "test",
            "acceptance": "acceptance",
            "production": "production",
        }
        execution_mode = execution_mode_map.get(run_mode, "strict")

        store = self._get_store()
        project = store.current_project()
        store.upsert_job(
            job_id=job_id,
            user_query=self.state.get("user_query", ""),
            project_id=str(project["id"]),
            status="running",
            current_phase="prepare_workspace",
            current_phase_idx=0,
            execution_mode=execution_mode,
            run_mode=run_mode,
            job_workspace=str(job.dir),
        )

        return {
            "job_id": job_id,
            "project_id": str(project["id"]),
            "run_mode": run_mode,
            "execution_mode": execution_mode,
            "workspace_root": str(ws.root),
            "job_workspace": str(job.dir),
            "retry_count": 0,
            "max_retries_reached": False,
            "errors": [],
            "current_node": "prepare_workspace",
        }

    async def _auto_remaining(self) -> None:
        """Execute all remaining auto phases, stopping at human_confirmation."""
        while self.current_phase_idx < len(_PIPELINE_PHASES):
            phase = _PIPELINE_PHASES[self.current_phase_idx]

            # Unified human-confirmation gate
            if phase == "human_confirmation" and not self.state.get("raw_human_response"):
                self.console.print("\n  [bold yellow]⚠ Human confirmation required[/bold yellow]")
                self.console.print("  [dim]Use /confirm to review assumptions.[/dim]\n")
                return

            success = await self._run_phase(phase)
            if not success:
                self.console.print(f"[red]Pipeline stopped at {phase}.[/red]")
                return

            # Post-g4_modeling confirmation check
            if phase == "g4_modeling" and self.state.get("human_confirmation_required"):
                n = self.state.get("unconfirmed_assumptions_count", "?")
                self.console.print(
                    "\n  [bold yellow]⚠ Human confirmation required[/bold yellow]"
                    f" — {n} assumptions"
                )
                self.console.print("  [dim]Use /confirm to review, then /step to continue.[/dim]\n")
                return

        self.console.print("\n[bold green]✓ Pipeline complete![/bold green]")

    # ── Rich rendering helpers ──────────────────────────────────────

    def _render_model_summary(self, model_ir: dict[str, Any]) -> None:
        """Render model IR as a Rich table."""
        ir_id = model_ir.get("model_ir_id", "N/A")
        self.console.print(f"\n[bold]Model IR:[/bold] {ir_id}")
        mode = model_ir.get("modeling_mode", "N/A")
        self.console.print(f"  Mode: {mode}")

        components = model_ir.get("components", [])
        if components:
            table = Table(title="Components")
            table.add_column("ID", style="cyan")
            table.add_column("Type", style="white")
            table.add_column("Material", style="green")
            table.add_column("Roles", style="yellow")

            for c in components:
                table.add_row(
                    c.get("component_id", "?"),
                    c.get("component_type", "?"),
                    c.get("material_id", "?"),
                    ", ".join(c.get("roles", [])),
                )
            self.console.print(table)

        sources = model_ir.get("sources", [])
        if sources:
            table = Table(title="Sources")
            table.add_column("ID", style="cyan")
            table.add_column("Particle", style="white")
            table.add_column("Energy", style="green")

            for s in sources:
                table.add_row(
                    s.get("source_id", "?"),
                    s.get("particle_type", "?"),
                    str(s.get("energy", "?")),
                )
            self.console.print(table)

        scoring = model_ir.get("scoring", [])
        if scoring:
            table = Table(title="Scoring")
            table.add_column("ID", style="cyan")
            table.add_column("Type", style="white")
            table.add_column("Volume", style="green")

            for sc in scoring:
                table.add_row(
                    sc.get("scoring_id", "?"),
                    sc.get("scoring_type", "?"),
                    sc.get("volume", "?"),
                )
            self.console.print(table)

    # ── Terminal input helpers ──────────────────────────────────────

    def _prompt_choice(
        self,
        prompt: str,
        choices: tuple[str, ...],
        default: str,
    ) -> str:
        """Prompt user to choose from a set of options."""
        while True:
            raw = input(f"  {prompt} [{default}] ").strip().lower()
            if not raw:
                return default
            if raw in choices:
                return raw
            print(f"  Invalid choice. Pick from: {', '.join(choices)}")

    def _prompt_text(self, prompt: str) -> str:
        """Prompt user for free-text input."""
        return input(prompt).strip()
