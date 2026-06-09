from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from agent_core.desktop import qml_main_path


def test_desktop_package_imports_without_pyside() -> None:
    module = importlib.import_module("agent_core.desktop")
    assert module.qml_main_path().name == "Main.qml"


def test_qml_main_exists_and_uses_service_bridge() -> None:
    path = qml_main_path()
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "ApplicationWindow" in text
    assert "radAgent.startJob" in text
    assert "radAgent.sendMessage" in text
    assert "RadAgent Workbench" in text


def test_desktop_optional_dependency_declared() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "desktop = [" in pyproject
    assert "PySide6" in pyproject
    assert 'radagent-desktop = "agent_core.desktop.app:main"' in pyproject


def test_bridge_requires_pyside_when_imported_without_qt() -> None:
    try:
        import PySide6  # noqa: F401
    except ImportError:
        with pytest.raises(RuntimeError, match="requires PySide6"):
            importlib.import_module("agent_core.desktop.bridge")
    else:
        bridge = importlib.import_module("agent_core.desktop.bridge")
        assert hasattr(bridge, "RadAgentBridge")
