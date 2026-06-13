from __future__ import annotations

import pytest
from agent_core.tui.app import (
    _copilot_model_candidates,
    _cycle_context_window,
    _format_context_window,
)
from agent_core.tui.commands import (
    CommandParseError,
    command_suggestions,
    input_mode_for_text,
    parse_command,
)


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


def test_visual_workbench_commands_are_parsed_and_validated() -> None:
    assert parse_command("/workbench").name == "workbench"
    assert parse_command("/workbench 100").args == "100"
    assert parse_command("/visual-approve").name == "visual-approve"
    reject = parse_command("/visual-reject target offset wrong")
    assert reject.name == "visual-reject"
    assert reject.args == "target offset wrong"

    with pytest.raises(CommandParseError, match="positive"):
        parse_command("/workbench 0")
    with pytest.raises(CommandParseError, match="Usage: /visual-reject"):
        parse_command("/visual-reject")


def test_human_confirmation_decision_commands_are_parsed_and_validated() -> None:
    reject = parse_command("/reject Geometry assumptions are wrong")
    assert reject.name == "reject"
    assert reject.args == "Geometry assumptions are wrong"

    ask_more = parse_command("/ask-more What detector pressure should be used?")
    assert ask_more.name == "ask-more"
    assert ask_more.args == "What detector pressure should be used?"

    with pytest.raises(CommandParseError, match="Usage: /reject"):
        parse_command("/reject")
    with pytest.raises(CommandParseError, match="Usage: /ask-more"):
        parse_command("/ask-more")


def test_human_confirmation_edit_command_is_parsed_and_validated() -> None:
    edit = parse_command("/edit-confirmation sources.primary.energy=200 unit=MeV")
    assert edit.name == "edit-confirmation"
    assert edit.args == "sources.primary.energy=200 unit=MeV"

    with pytest.raises(CommandParseError, match="Usage: /edit-confirmation"):
        parse_command("/edit-confirmation")


def test_unknown_command_is_rejected() -> None:
    with pytest.raises(CommandParseError, match="Unknown command"):
        parse_command("/banana")


def test_aliases() -> None:
    assert parse_command("?").name == "help"
    assert parse_command("/q").name == "exit"
    assert parse_command("/sim 5").name == "simulate"
    assert parse_command("/status").name == "status"
    assert parse_command("/check").name == "check"


def test_options_command_accepts_optional_language_and_settings_alias() -> None:
    assert parse_command("/options").name == "options"
    assert parse_command("/option").name == "options"
    assert parse_command("/settings").name == "options"
    command = parse_command("/options zh")
    assert command.name == "options"
    assert command.args == "zh"


def test_workstation_commands_are_parsed() -> None:
    assert parse_command("/open report").name == "open"
    assert parse_command("/report").name == "report"
    assert parse_command("/demo geant4").name == "demo"
    assert parse_command("/history electron").name == "history"
    assert parse_command("/mode run").name == "mode"
    assert parse_command("/job job-001").name == "job"
    assert parse_command("/retry job-002").name == "retry"

    with pytest.raises(CommandParseError, match="Usage: /demo"):
        parse_command("/demo")

    with pytest.raises(CommandParseError, match="Usage: /job"):
        parse_command("/job")

    with pytest.raises(CommandParseError, match="Usage: /retry"):
        parse_command("/retry")

    with pytest.raises(CommandParseError, match="ask, run, cmd, inspect, artifact, config"):
        parse_command("/mode unknown")


def test_command_suggestions_return_stable_palette_entries() -> None:
    suggestions = command_suggestions("/")

    assert suggestions[0].startswith("/run")
    assert any(item.startswith("/check") for item in suggestions)
    assert any(item.startswith("/open") for item in suggestions)
    assert any(item.startswith("/report") for item in suggestions)
    assert any(item.startswith("/demo") for item in suggestions)
    assert len(suggestions) <= 12

    assert command_suggestions("/re") == [
        "/report    Generate or preview the active report",
        "/resume    Resume a saved job",
        "/retry     Retry a saved job",
        "/revise    Request a revision for the active job",
        "/revisions List saved revisions",
    ]


def test_input_mode_for_text_distinguishes_ask_run_and_command() -> None:
    assert input_mode_for_text("Explain current workspace") == "ASK"
    assert input_mode_for_text("/check tools") == "CMD"
    assert input_mode_for_text("/run 7 MeV electron through aluminum") == "RUN"


def test_copilot_model_candidates_include_current_models_and_common_mimo_options() -> None:
    candidates = _copilot_model_candidates(
        {
            "lite": "mimo-v2.5",
            "pro": "mimo-v2.5-pro",
            "max": "custom-review-model",
        }
    )

    assert candidates[:3] == ["mimo-v2.5-pro", "mimo-v2.5", "custom-review-model"]
    assert "mimo-v2.5-pro" in candidates
    assert len(candidates) == len(set(candidates))


def test_copilot_context_window_cycles_standard_values_and_formats_labels() -> None:
    assert _cycle_context_window(100_000, 1) == 200_000
    assert _cycle_context_window(200_000, 1) == 500_000
    assert _cycle_context_window(500_000, 1) == 1_000_000
    assert _cycle_context_window(1_000_000, 1) == 100_000
    assert _cycle_context_window(128_000, 1) == 100_000
    assert _cycle_context_window(100_000, -1) == 1_000_000
    assert _format_context_window(1_000_000) == "1m"
    assert _format_context_window(128_000) == "128k"
