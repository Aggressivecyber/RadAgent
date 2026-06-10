"""Tests for agent_core.models.gateway — model gateway."""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from agent_core.models.client import call_openai_compatible_model
from agent_core.models.gateway import get_model_gateway, reset_model_gateway
from agent_core.models.schemas import (
    ModelCallRequest,
    ModelCallResult,
    ModelProfile,
    ModelProvider,
    ModelTask,
    ModelTier,
)


@pytest.fixture(autouse=True)
def reset_gateway() -> None:
    """Reset gateway singleton around each test."""
    reset_model_gateway()
    yield
    reset_model_gateway()


class TestModelGateway:
    """Verify ModelGateway behavior."""

    def test_singleton_creation(self) -> None:
        """get_model_gateway should return same instance."""
        gw1 = get_model_gateway()
        gw2 = get_model_gateway()
        assert gw1 is gw2

    def test_singleton_reset(self) -> None:
        """reset_model_gateway should create new instance."""
        gw1 = get_model_gateway()
        reset_model_gateway()
        gw2 = get_model_gateway()
        assert gw1 is not gw2

    @pytest.mark.asyncio
    async def test_call_returns_result(self) -> None:
        """Gateway call should return ModelCallResult."""
        gw = get_model_gateway()

        mock_content = '{"intent": "smalltalk"}'
        mock_usage = {"prompt_tokens": 10, "completion_tokens": 5}

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(mock_content, mock_usage),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                response_format="json",
            )

        assert isinstance(result, ModelCallResult)
        assert result.task == ModelTask.INTENT_ROUTING
        assert result.tier == ModelTier.LITE  # INTENT_ROUTING defaults to LITE
        assert result.content == mock_content
        assert result.parsed_json == {"intent": "smalltalk"}
        assert result.usage == mock_usage
        assert result.error is None

    @pytest.mark.asyncio
    async def test_call_with_explicit_tier(self) -> None:
        """Gateway should use explicit tier when provided."""
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=("ok", {}),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                tier=ModelTier.MAX,
            )

        assert result.tier == ModelTier.MAX

    @pytest.mark.asyncio
    async def test_call_handles_error(self) -> None:
        """Gateway should handle errors gracefully."""
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API error"),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
            )

        assert result.error == "API error"
        assert result.content == ""
        assert result.parsed_json is None

    @pytest.mark.asyncio
    async def test_call_times_out_stalled_provider(self) -> None:
        """Gateway should fail stalled provider calls instead of hanging forever."""
        gw = get_model_gateway()
        gw.profiles[ModelTier.LITE].timeout_s = 0.01
        gw.profiles[ModelTier.LITE].max_retries = 0

        async def stalled_call(*args, **kwargs):
            await asyncio.sleep(10.0)
            return "unreachable", {}

        with patch.dict("os.environ", {"RADAGENT_ENABLE_MODEL_TIMEOUTS": "1"}), patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            side_effect=stalled_call,
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
            )

        assert result.error
        assert "timed out" in result.error
        assert result.content == ""

    @pytest.mark.asyncio
    async def test_call_json_parse(self) -> None:
        """Gateway should parse JSON responses."""
        gw = get_model_gateway()

        json_content = '{"key": "value"}'
        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(json_content, {}),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                response_format="json",
            )

        assert result.parsed_json == {"key": "value"}

    @pytest.mark.asyncio
    async def test_call_json_parse_with_markdown(self) -> None:
        """Gateway should extract JSON from markdown code fences."""
        gw = get_model_gateway()

        json_content = '```json\n{"key": "value"}\n```'
        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=(json_content, {}),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
                response_format="json",
            )

        assert result.parsed_json == {"key": "value"}

    @pytest.mark.asyncio
    async def test_gateway_applies_default_thinking_by_task(self) -> None:
        """Gateway should add MiMo thinking metadata when callers omit it."""
        gw = get_model_gateway()
        captured_requests = []

        async def fake_call(profile, req):
            captured_requests.append(req)
            return "{}", {}

        with patch("agent_core.models.gateway.call_openai_compatible_model", fake_call):
            await gw.call(
                task=ModelTask.G4_MODELING,
                system_prompt="test",
                user_prompt="build model",
                response_format="json",
            )
            await gw.call(
                task=ModelTask.SIMPLE_EXTRACTION,
                system_prompt="test",
                user_prompt="name it",
            )

        assert captured_requests[0].metadata["enable_thinking"] is True
        assert captured_requests[1].metadata["enable_thinking"] is False

    @pytest.mark.asyncio
    async def test_gateway_preserves_explicit_thinking_override(self) -> None:
        """Node-level metadata can still override the task default."""
        gw = get_model_gateway()
        captured_requests = []

        async def fake_call(profile, req):
            captured_requests.append(req)
            return "{}", {}

        with patch("agent_core.models.gateway.call_openai_compatible_model", fake_call):
            await gw.call(
                task=ModelTask.CODEGEN,
                system_prompt="test",
                user_prompt="summarize context",
                metadata={"enable_thinking": False},
            )

        assert captured_requests[0].metadata["enable_thinking"] is False

    @pytest.mark.asyncio
    async def test_call_writes_job_scoped_transcript(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gateway should persist prompt/response transcript artifacts for observability."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=('{"ok": true}', {"prompt_tokens": 3}),
        ):
            result = await gw.call(
                task=ModelTask.CODEGEN,
                system_prompt="system secret api_key=abc",
                user_prompt="user context",
                response_format="json",
                metadata={"job_id": "transcript_job", "module_name": "simulation_core"},
            )

        assert result.error is None
        job_dir = tmp_path / "jobs" / "transcript_job"
        active = json.loads((job_dir / "logs" / "active_model_call.json").read_text())
        transcript_path = job_dir / active["transcript_path"]
        transcript = json.loads(transcript_path.read_text())

        assert transcript["status"] == "passed"
        assert transcript["request"]["user_prompt"] == "user context"
        assert transcript["request"]["system_prompt"] == "system secret api_key=<redacted>"
        assert transcript["result"]["parsed_json"] == {"ok": True}

        events = (job_dir / "logs" / "events.jsonl").read_text().splitlines()
        payloads = [json.loads(line) for line in events]
        assert [event["event_type"] for event in payloads] == [
            "model_call_start",
            "model_call",
        ]
        assert payloads[0]["artifacts"][0]["path"] == active["transcript_path"]

    @pytest.mark.asyncio
    async def test_tool_log_failure_is_visible_but_non_blocking(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Observability failures should not hide silently or fail the model call."""
        gw = get_model_gateway()

        with (
            patch(
                "agent_core.models.gateway.call_openai_compatible_model",
                new_callable=AsyncMock,
                return_value=("ok", {}),
            ),
            patch(
                "agent_core.models.tool_logger.get_tool_logger",
                side_effect=RuntimeError("logger unavailable"),
            ),
            caplog.at_level(logging.WARNING, logger="agent_core.models.gateway"),
        ):
            result = await gw.call(
                task=ModelTask.INTENT_ROUTING,
                system_prompt="test",
                user_prompt="hello",
            )

        assert result.error is None
        assert "Failed to write model tool-call log: logger unavailable" in caplog.text

    @pytest.mark.asyncio
    async def test_mimo_token_plan_payload_thinking_and_reasoning_capture(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_payloads = []
        captured_headers = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": '{"ok": true}',
                                "reasoning_content": "checked build errors and interfaces",
                            }
                        }
                    ],
                    "usage": {"total_tokens": 42},
                }

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, headers, json):
                captured_headers.append(headers)
                captured_payloads.append(json)
                return FakeResponse()

        monkeypatch.setenv("RADAGENT_API_KEY", "tp-test")
        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        profile = ModelProfile(
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="mimo-v2.5-pro",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            api_key_env="RADAGENT_API_KEY",
        )
        request = ModelCallRequest(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            system_prompt="system",
            user_prompt="user",
            response_format="json",
            metadata={"enable_thinking": True},
        )

        content, usage = await call_openai_compatible_model(profile, request)

        assert content == '{"ok": true}'
        assert captured_headers[0]["api-key"] == "tp-test"
        assert "Authorization" not in captured_headers[0]
        assert "max_tokens" not in captured_payloads[0]
        assert captured_payloads[0]["max_completion_tokens"] == profile.max_tokens
        assert "temperature" not in captured_payloads[0]
        assert "reasoning_effort" not in captured_payloads[0]
        assert captured_payloads[0]["thinking"] == {"type": "enabled"}
        assert usage["reasoning_content"] == "checked build errors and interfaces"

    @pytest.mark.asyncio
    async def test_mimo_token_plan_payload_disables_thinking_for_simple_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured_payloads = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return None

            async def post(self, url, headers, json):
                captured_payloads.append(json)
                return FakeResponse()

        monkeypatch.setenv("RADAGENT_API_KEY", "tp-test")
        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        profile = ModelProfile(
            tier=ModelTier.LITE,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="mimo-v2.5",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            api_key_env="RADAGENT_API_KEY",
        )
        request = ModelCallRequest(
            task=ModelTask.SIMPLE_EXTRACTION,
            tier=ModelTier.LITE,
            system_prompt="system",
            user_prompt="user",
        )

        content, _usage = await call_openai_compatible_model(profile, request)

        assert content == "ok"
        assert captured_payloads[0]["thinking"] == {"type": "disabled"}
        assert captured_payloads[0]["temperature"] == profile.temperature

    @pytest.mark.asyncio
    async def test_token_plan_missing_access_key_fails_before_http_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class FakeClient:
            def __init__(self, **kwargs):
                raise AssertionError("http client should not be created")

        monkeypatch.delenv("RADAGENT_API_KEY", raising=False)
        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        profile = ModelProfile(
            tier=ModelTier.MAX,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="mimo-v2.5-pro",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            api_key_env="RADAGENT_API_KEY",
        )
        request = ModelCallRequest(
            task=ModelTask.CODEGEN,
            tier=ModelTier.MAX,
            system_prompt="system",
            user_prompt="user",
        )

        with pytest.raises(RuntimeError, match="Missing API key env: RADAGENT_API_KEY"):
            await call_openai_compatible_model(profile, request)
