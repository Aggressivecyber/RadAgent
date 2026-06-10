from __future__ import annotations

import pytest
from agent_core.app import RadAgentAppService
from agent_core.tui.app import create_app_class

pytest.importorskip("textual")


@pytest.mark.asyncio
async def test_textual_app_mounts_and_opens_help(tmp_path) -> None:
    app_cls = create_app_class()
    app = app_cls(service=RadAgentAppService(workspace_root=tmp_path))

    async with app.run_test() as pilot:
        await pilot.pause()

        header = app.query_one("#header")
        assert "RadAgent" in str(header.content)
        assert "phase:idle" in str(header.content)

        await pilot.press("f1")
        await pilot.pause()

        inspector = app.query_one("#inspector")
        assert "visible" in inspector.classes

        app.service._emit(
            "phase_started",
            status="running",
            phase="context",
            summary="Running context",
        )
        await pilot.pause()

        assert any(row.phase == "context" for row in app._rows)

        full_message = "**bold answer**\n\n- one\n- two"
        app.service._emit(
            "chat_finished",
            status="success",
            summary=full_message[:10],
            payload={"message": full_message},
        )
        await pilot.pause()

        assert app._rows[-1].summary == full_message
        assert app.query("Markdown")
