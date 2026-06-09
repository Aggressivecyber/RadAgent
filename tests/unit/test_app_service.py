from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from agent_core.app import PIPELINE_PHASES, RadAgentAppService


def test_service_exposes_pipeline_contract(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)

    assert PIPELINE_PHASES[0] == "prepare_workspace"
    status = service.get_status()
    assert status.status == "idle"
    assert status.workspace_root == str(tmp_path)


@pytest.mark.asyncio
async def test_prepare_workspace_phase_persists_job_and_events(tmp_path, monkeypatch) -> None:
    async def fake_build_job_id(base_id: str, user_query: str) -> str:
        assert base_id == ""
        assert user_query == "build detector"
        return "job_frontend_test"

    monkeypatch.setattr("agent_core.naming.build_job_id", fake_build_job_id)
    events = []
    service = RadAgentAppService(workspace_root=tmp_path, event_callback=events.append)
    service.state = {
        "user_query": "build detector",
        "job_id": "",
        "run_mode": "strict",
        "execution_mode": "strict",
        "errors": [],
    }

    result = await service.run_phase("prepare_workspace")

    assert result.success is True
    assert result.status.job_id == "job_frontend_test"
    assert result.status.current_phase == "context"
    assert (tmp_path / "jobs" / "job_frontend_test" / "00_input" / "user_query.md").is_file()
    assert service.store.get_job("job_frontend_test") is not None
    assert [event.event_type for event in events] == ["phase_started", "phase_finished"]


def test_read_artifact_supports_text_json_binary_and_missing(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    text_path = tmp_path / "report.md"
    json_path = tmp_path / "data.json"
    binary_path = tmp_path / "image.bin"
    text_path.write_text("hello", encoding="utf-8")
    json_path.write_text('{"ok": true}', encoding="utf-8")
    binary_path.write_bytes(b"\x00\x01")

    text = service.read_artifact(str(text_path))
    data = service.read_artifact(str(json_path))
    binary = service.read_artifact(str(binary_path))
    missing = service.read_artifact(str(tmp_path / "missing.txt"))

    assert text.kind == "text"
    assert text.text == "hello"
    assert data.kind == "json"
    assert data.json_data == {"ok": True}
    assert binary.kind == "binary"
    assert missing.exists is False


@pytest.mark.asyncio
async def test_chat_emits_events_without_ui_dependency(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    agent = AsyncMock()
    agent.chat.return_value = "answer"
    service._chat_agent = agent

    response = await service.chat("question")

    assert response.message == "answer"
    assert [event.event_type for event in response.events] == [
        "chat_started",
        "chat_finished",
    ]
    agent.chat.assert_awaited_once_with("question")
