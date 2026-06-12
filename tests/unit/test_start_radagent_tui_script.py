from __future__ import annotations

from pathlib import Path

SCRIPT = Path("start-radagent-tui.sh")


def test_start_tui_script_bootstraps_venv_and_tui_extra() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "python3 -m venv .venv" in text
    assert "source \".venv/bin/activate\"" in text
    assert "python -m pip install -e '.[tui]'" in text


def test_start_tui_script_checks_full_tui_import_before_launching() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "check_tui_imports" in text
    assert "import textual" in text
    assert "from agent_core.tui.app import create_app_class" in text


def test_start_tui_script_launches_module_through_active_venv() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "exec python -m agent_core.tui \"$@\"" in text
    assert "radagent-tui \"$@\"" not in text


def test_start_tui_script_supports_setup_and_check_modes() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--setup" in text
    assert "--check" in text
    assert "ACTION=\"setup\"" in text
    assert "ACTION=\"check\"" in text
