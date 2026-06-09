from __future__ import annotations

import sys
from pathlib import Path


def qml_main_path() -> Path:
    return Path(__file__).resolve().parent / "qml" / "Main.qml"


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:
        raise RuntimeError(
            "RadAgent desktop requires PySide6. Install with: pip install -e '.[desktop]'"
        ) from exc

    from agent_core.desktop.bridge import RadAgentBridge

    app = QGuiApplication(argv)
    app.setApplicationDisplayName("RadAgent")
    app.setOrganizationName("RadAgent")

    engine = QQmlApplicationEngine()
    bridge = RadAgentBridge()
    engine.rootContext().setContextProperty("radAgent", bridge)
    engine.load(QUrl.fromLocalFile(str(qml_main_path())))

    if not engine.rootObjects():
        return 1
    return app.exec()
