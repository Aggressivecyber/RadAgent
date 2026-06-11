from __future__ import annotations

from agent_core.tui.models import Command


class CommandParseError(ValueError):
    """Raised when composer input looks like a command but is invalid."""


_ALIASES = {
    "?": "help",
    "q": "exit",
    "quit": "exit",
    "sim": "simulate",
    "status": "inspect",
    "log": "logs",
    "option": "options",
    "opts": "options",
    "setting": "options",
    "settings": "options",
    "config": "options",
}

_KNOWN_COMMANDS = {
    "artifact",
    "artifacts",
    "build",
    "chat",
    "confirm",
    "credibility",
    "exit",
    "gates",
    "help",
    "inspect",
    "jobs",
    "logs",
    "memory",
    "model",
    "options",
    "project",
    "projects",
    "accept-revision",
    "reject-revision",
    "revision",
    "revisions",
    "revise",
    "resume",
    "run",
    "simulate",
    "step",
}

_REQUIRES_ARGS = {
    "artifact": "Usage: /artifact <path>",
    "chat": "Usage: /chat <message>",
    "project": "Usage: /project <slug-or-id>",
    "accept-revision": "Usage: /accept-revision <revision_id>",
    "reject-revision": "Usage: /reject-revision <revision_id>",
    "revision": "Usage: /revision <revision_id>",
    "revise": "Usage: /revise <change request>",
    "resume": "Usage: /resume <job_id>",
    "run": "Usage: /run <simulation request>",
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
    if name == "simulate" and args:
        try:
            events = int(args)
        except ValueError as exc:
            raise CommandParseError("Usage: /simulate [positive event count]") from exc
        if events <= 0:
            raise CommandParseError("Simulation event count must be positive.")

    return Command(name=name, args=args, raw=text)
