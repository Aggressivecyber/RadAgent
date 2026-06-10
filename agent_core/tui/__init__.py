"""Terminal-native RadAgent frontend package.

The package is safe to import without Textual installed. The Textual runtime
is loaded only by the `radagent-tui` entry point.
"""

from agent_core.tui.adapters import event_to_row, status_to_header
from agent_core.tui.commands import Command, CommandParseError, parse_command
from agent_core.tui.models import HeaderState, TimelineRow

__all__ = [
    "Command",
    "CommandParseError",
    "HeaderState",
    "TimelineRow",
    "event_to_row",
    "parse_command",
    "status_to_header",
]
