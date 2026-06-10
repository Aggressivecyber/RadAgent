from __future__ import annotations


def test_tui_package_imports_without_textual_runtime() -> None:
    import agent_core.tui as tui
    import agent_core.tui.app as app

    assert callable(tui.parse_command)
    assert callable(app.main)


def test_tui_main_help_does_not_start_app(capsys) -> None:
    from agent_core.tui.app import main

    assert main(["--help"]) == 0

    output = capsys.readouterr().out
    assert "--theme radagent|slate|mono" in output


def test_tui_main_rejects_unknown_theme(capsys) -> None:
    from agent_core.tui.app import main

    assert main(["--theme", "unknown"]) == 2

    error = capsys.readouterr().err
    assert "--theme radagent|slate|mono" in error


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
