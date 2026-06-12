from __future__ import annotations

from agent_core.tui.models import Command


class CommandParseError(ValueError):
    """Raised when composer input looks like a command but is invalid."""


_ALIASES = {
    "?": "help",
    "approval": "approve",
    "artifact-browser": "artifacts",
    "check-tools": "check",
    "q": "exit",
    "quit": "exit",
    "sim": "simulate",
    "status": "status",
    "log": "logs",
    "option": "options",
    "opts": "options",
    "setting": "options",
    "settings": "options",
    "config": "options",
    "visualize": "workbench",
}

_COMMAND_DESCRIPTIONS = {
    "run": "Create and run a simulation task",
    "approve": "Approve active human confirmation",
    "check": "Inspect Geant4 / TCAD / ngspice",
    "open": "Open artifacts or preview a named output",
    "report": "Generate or preview the active report",
    "demo": "Play a safe demo workflow",
    "help": "Show command help",
    "history": "Search command history",
    "jobs": "Browse saved jobs",
    "job": "Open one job detail",
    "artifacts": "Browse logs, reports, plots, and outputs",
    "inspect": "Open tool inspection details",
    "status": "Show active job status",
    "mode": "Switch composer mode",
    "resume": "Resume a saved job",
    "retry": "Retry a saved job",
    "revise": "Request a revision for the active job",
    "revisions": "List saved revisions",
    "artifact": "Preview one artifact path",
    "build": "Build generated code",
    "chat": "Ask RadAgent directly",
    "confirm": "Open confirmation review",
    "credibility": "Open credibility report",
    "exit": "Exit the TUI",
    "gates": "Open gate results",
    "logs": "Open service event log",
    "memory": "Open workflow memory",
    "model": "View or update model settings",
    "options": "Open language/theme options",
    "project": "Switch project",
    "projects": "List projects",
    "accept-revision": "Accept a saved revision",
    "reject-revision": "Reject a saved revision",
    "revision": "Open one revision",
    "simulate": "Run the generated simulator",
    "visual-approve": "Approve G4 visual review",
    "visual-reject": "Reject G4 visual review",
    "workbench": "Open the G4 visual workbench",
    "step": "Run the next pipeline phase",
}
_KNOWN_COMMANDS = set(_COMMAND_DESCRIPTIONS)
_PALETTE_ORDER = (
    "run",
    "check",
    "open",
    "report",
    "demo",
    "help",
    "history",
    "jobs",
    "job",
    "artifacts",
    "inspect",
    "status",
    "mode",
    "resume",
    "retry",
    "workbench",
    "revise",
    "revisions",
)
_MODES = frozenset({"ask", "run", "cmd", "inspect", "artifact", "config"})

_REQUIRES_ARGS = {
    "artifact": "Usage: /artifact <path>",
    "chat": "Usage: /chat <message>",
    "demo": "Usage: /demo <geant4|tcad|ngspice|neutron-ct|electron-dose>",
    "job": "Usage: /job <job_id>",
    "project": "Usage: /project <slug-or-id>",
    "accept-revision": "Usage: /accept-revision <revision_id>",
    "reject-revision": "Usage: /reject-revision <revision_id>",
    "revision": "Usage: /revision <revision_id>",
    "revise": "Usage: /revise <change request>",
    "resume": "Usage: /resume <job_id>",
    "retry": "Usage: /retry <job_id>",
    "run": "Usage: /run <simulation request>",
    "visual-reject": "Usage: /visual-reject <reason>",
}


def parse_command(text: str) -> Command:
    """Parse composer input into a local command.

    Plain text is always treated as chat. Slash commands remain deterministic
    and do not depend on intent classification.
    """
    stripped = text.strip()
    if not stripped:
        raise CommandParseError("Enter a message or command.")
    if stripped == "?":
        return Command(name="help", raw=text)
    if not stripped.startswith("/"):
        return Command(name="chat", args=stripped, raw=text)

    head, _, args = stripped.partition(" ")
    name = head[1:].lower()
    if not name:
        raise CommandParseError("Enter a command after '/'.")
    name = _ALIASES.get(name, name)
    args = args.strip()

    if name not in _KNOWN_COMMANDS:
        raise CommandParseError(f"Unknown command: /{name}")
    if name in _REQUIRES_ARGS and not args:
        raise CommandParseError(_REQUIRES_ARGS[name])
    if name == "mode":
        selected = args.lower()
        if selected not in _MODES:
            raise CommandParseError(
                "Usage: /mode <ask, run, cmd, inspect, artifact, config>"
            )
    if name == "simulate" and args:
        try:
            events = int(args)
        except ValueError as exc:
            raise CommandParseError("Usage: /simulate [positive event count]") from exc
        if events <= 0:
            raise CommandParseError("Simulation event count must be positive.")
    if name == "workbench" and args:
        try:
            events = int(args)
        except ValueError as exc:
            raise CommandParseError("Usage: /workbench [positive event count]") from exc
        if events <= 0:
            raise CommandParseError("Workbench event count must be positive.")

    return Command(name=name, args=args, raw=text)


def command_suggestions(prefix: str, *, limit: int = 12) -> list[str]:
    """Return stable command-palette entries for the composer prefix."""
    normalized = prefix.strip().lower()
    if normalized.startswith("/"):
        normalized = normalized[1:]
    matches: list[str] = []
    for name in _PALETTE_ORDER:
        if normalized and not name.startswith(normalized):
            continue
        matches.append(f"/{name:<9} {_COMMAND_DESCRIPTIONS[name]}")
        if len(matches) >= limit:
            break
    return matches


def input_mode_for_text(text: str) -> str:
    """Return the visible composer mode label for the current text."""
    stripped = text.strip()
    if stripped.startswith("/run"):
        return "RUN"
    if stripped.startswith("/"):
        return "CMD"
    return "ASK"
