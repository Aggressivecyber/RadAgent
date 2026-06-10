from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from agent_core.app import PIPELINE_PHASES, RadAgentAppService
from agent_core.models.schemas import ModelTier
from agent_core.workspace.paths import STAGE_INPUT
from pydantic import ValidationError


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
    assert (tmp_path / "jobs" / "job_frontend_test" / STAGE_INPUT / "user_query.md").is_file()
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


def test_read_artifact_reports_invalid_json_without_blocking_text_view(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    json_path = tmp_path / "broken.json"
    json_path.write_text('{"ok": ', encoding="utf-8")

    content = service.read_artifact(str(json_path))

    assert content.kind == "text"
    assert content.text == '{"ok": '
    assert content.json_data is None
    assert content.errors
    assert content.errors[0].startswith("Invalid JSON:")


@pytest.mark.asyncio
async def test_chat_emits_events_without_ui_dependency(tmp_path, monkeypatch) -> None:
    service = RadAgentAppService(workspace_root=tmp_path)
    agent = AsyncMock()
    long_answer = "x" * 300
    agent.chat.return_value = long_answer
    service._chat_agent = agent

    response = await service.chat("question")

    assert response.message == long_answer
    assert [event.event_type for event in response.events] == [
        "copilot_started",
        "copilot_finished",
    ]
    assert response.events[0].payload["message"] == "question"
    assert len(response.events[1].summary) == 120
    assert response.events[1].payload["message"] == long_answer
    agent.chat.assert_awaited_once()
    args, kwargs = agent.chat.await_args
    assert args == ("question",)
    assert kwargs["workflow_context"]["status"] == "idle"


def test_service_exposes_frontend_safe_model_config(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "RADAGENT_MODEL_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1",
                "RADAGENT_API_KEY=secret-key",
                "RADAGENT_MODEL_PRO=mimo-v2.5-pro",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_API_KEY", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_PRO", raising=False)
    service = RadAgentAppService(workspace_root=tmp_path, env_path=env_file)

    config = service.get_model_config()

    assert config.tiers[ModelTier.PRO.value].model_name == "mimo-v2.5-pro"
    assert config.tiers[ModelTier.PRO.value].base_url == "https://token-plan-cn.xiaomimimo.com/v1"
    assert config.tiers[ModelTier.PRO.value].api_key_configured is True
    assert "secret-key" not in config.model_dump_json()


def test_service_updates_model_config_for_frontend(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    events = []
    monkeypatch.delenv("RADAGENT_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("RADAGENT_API_KEY", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_LITE", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_PRO", raising=False)
    monkeypatch.delenv("RADAGENT_MODEL_MAX", raising=False)
    service = RadAgentAppService(
        workspace_root=tmp_path,
        env_path=env_file,
        event_callback=events.append,
    )

    config = service.update_model_config(
        {
            "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
            "api_key": "tp-test-key",
            "lite_model": "mimo-v2.5",
            "pro_model": "mimo-v2.5-pro",
            "max_model": "mimo-v2.5-pro",
        }
    )

    text = env_file.read_text(encoding="utf-8")
    assert "RADAGENT_MODEL_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1" in text
    assert "RADAGENT_API_KEY=tp-test-key" in text
    assert config.tiers[ModelTier.LITE.value].model_name == "mimo-v2.5"
    assert config.tiers[ModelTier.PRO.value].api_key_configured is True
    assert "provider" not in config.tiers[ModelTier.PRO.value].model_dump()
    assert events[-1].event_type == "model_config_updated"


def test_service_rejects_provider_in_frontend_model_config(tmp_path) -> None:
    service = RadAgentAppService(workspace_root=tmp_path, env_path=tmp_path / ".env")

    with pytest.raises(ValidationError):
        service.update_model_config({"provider": "mock"})
