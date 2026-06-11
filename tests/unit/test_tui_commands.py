from __future__ import annotations

import pytest
from agent_core.tui.commands import CommandParseError, parse_command


def test_plain_text_defaults_to_chat() -> None:
    command = parse_command("How should I choose a physics list?")

    assert command.name == "chat"
    assert command.args == "How should I choose a physics list?"


def test_run_command_requires_query() -> None:
    with pytest.raises(CommandParseError, match="Usage: /run"):
        parse_command("/run")


def test_simulate_validates_positive_count() -> None:
    assert parse_command("/simulate 1000").args == "1000"

    with pytest.raises(CommandParseError, match="positive"):
        parse_command("/simulate 0")


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(CommandParseError, match="Unknown command"):
        parse_command("/banana")


def test_aliases() -> None:
    assert parse_command("?").name == "help"
    assert parse_command("/q").name == "exit"
    assert parse_command("/sim 5").name == "simulate"


def test_options_command_accepts_optional_language_and_settings_alias() -> None:
    assert parse_command("/options").name == "options"
    assert parse_command("/option").name == "options"
    assert parse_command("/settings").name == "options"
    command = parse_command("/options zh")
    assert command.name == "options"
    assert command.args == "zh"
