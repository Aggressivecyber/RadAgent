from __future__ import annotations


def test_tui_main_reports_missing_textual_dependency(monkeypatch, capsys) -> None:
    import builtins

    from agent_core.tui.app import main

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "textual" or name.startswith("textual."):
            raise ModuleNotFoundError("No module named 'textual'", name="textual")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert main(["--mode", "test"]) == 1

    error = capsys.readouterr().err
    assert "requires the optional Textual dependency" in error
    assert "pip install -e '.[tui]'" in error


def test_tui_package_imports_without_textual_runtime() -> None:
    import agent_core.tui as tui
    import agent_core.tui.app as app

    assert callable(tui.parse_command)
    assert callable(app.main)


def test_tui_main_help_does_not_start_app(capsys) -> None:
    from agent_core.tui.app import main

    assert main(["--help"]) == 0

    output = capsys.readouterr().out
    assert "--theme slate-workstation|neon-lab|minimal-terminal" in output


def test_tui_main_rejects_unknown_theme(capsys) -> None:
    from agent_core.tui.app import main

    assert main(["--theme", "unknown"]) == 2

    error = capsys.readouterr().err
    assert "--theme slate-workstation|neon-lab|minimal-terminal" in error


def test_default_theme_uses_slate_workstation_tokens_and_weak_borders() -> None:
    from agent_core.tui.app import _THEMES, _css_for_theme

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


def test_tui_model_config_arg_parser() -> None:
    from agent_core.tui.app import _parse_model_config_args

    parsed = _parse_model_config_args(
        "url=https://token-plan-cn.xiaomimimo.com/v1 "
        "key=tp-test lite=mimo-v2.5 pro=mimo-v2.5-pro max_tokens=12000"
    )

    assert parsed == {
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "api_key": "tp-test",
        "lite_model": "mimo-v2.5",
        "pro_model": "mimo-v2.5-pro",
        "max_max_tokens": 12000,
    }


def test_tui_model_config_arg_parser_accepts_common_context_windows() -> None:
    from agent_core.tui.app import _parse_model_config_args

    parsed = _parse_model_config_args("lite_window=100k pro_window=500k max_window=1m")

    assert parsed == {
        "lite_context_window_tokens": 100_000,
        "pro_context_window_tokens": 500_000,
        "max_context_window_tokens": 1_000_000,
    }


def test_tui_model_config_arg_parser_rejects_unlisted_context_window() -> None:
    from agent_core.tui.app import _parse_model_config_args

    parsed = _parse_model_config_args("max_window=128k")

    assert parsed == {"max_context_window_tokens": 128_000}


def test_tui_model_config_arg_parser_treats_bare_custom_window_as_k_units() -> None:
    from agent_core.tui.app import _parse_model_config_args

    parsed = _parse_model_config_args("max_window=750")

    assert parsed == {"max_context_window_tokens": 750_000}


def test_tui_options_model_config_help_lines_are_discoverable() -> None:
    from agent_core.tui.app import _model_config_help_lines

    lines = _model_config_help_lines()
    text = "\n".join(lines)

    assert "Model" in text
    assert "/model url=" in text
    assert "lite=" in text
    assert "pro=" in text
    assert "max_window=" in text


def test_tui_extracts_simulation_briefing_query_from_copilot_result() -> None:
    from types import SimpleNamespace

    from agent_core.tui.app import _simulation_briefing_query_from_result

    result = SimpleNamespace(
        commands=[
            {
                "name": "start_simulation_briefing",
                "args": {"query": "建立一个 Geant4 质子束仿真"},
                "risk": "write",
                "status": "pending_confirmation",
            }
        ]
    )

    assert _simulation_briefing_query_from_result(result) == "建立一个 Geant4 质子束仿真"
