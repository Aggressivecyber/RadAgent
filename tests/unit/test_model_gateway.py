"""Tests for agent_core.models.gateway — model gateway."""

from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, patch

import pytest
from agent_core.models.client import call_openai_compatible_model, call_openai_compatible_tools
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
    from agent_core.models.client import reset_model_http_clients

    reset_model_gateway()
    reset_model_http_clients()
    yield
    reset_model_http_clients()
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
        assert result.reasoning_content == ""
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
    async def test_call_json_parse_array(self) -> None:
        """Gateway should preserve JSON arrays in parsed_json."""
        gw = get_model_gateway()

        json_content = '[{"component_id": "world"}]'
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

        assert result.error is None
        assert result.parsed_json == [{"component_id": "world"}]

    @pytest.mark.asyncio
    async def test_gateway_applies_default_thinking_by_task(self) -> None:
        """Gateway should add MiMo thinking metadata when callers omit it."""
        gw = get_model_gateway()
        captured_requests = []

        async def fake_call(profile, req, **_kwargs):
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
    async def test_gateway_preserves_public_reasoning_content_outside_usage(self) -> None:
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=("ok", {"total_tokens": 42}, "public reasoning summary"),
        ):
            result = await gw.call(
                task=ModelTask.CODEGEN,
                system_prompt="test",
                user_prompt="build",
            )

        assert result.content == "ok"
        assert result.reasoning_content == "public reasoning summary"
        assert result.usage == {"total_tokens": 42}
        assert result.usage.get("reasoning_content") is None

    @pytest.mark.asyncio
    async def test_gateway_preserves_explicit_thinking_override(self) -> None:
        """Node-level metadata can still override the task default."""
        gw = get_model_gateway()
        captured_requests = []

        async def fake_call(profile, req, **_kwargs):
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
    async def test_openai_compatible_stream_updates_transcript_progress(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Gateway should persist partial response chunks before the call completes."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        monkeypatch.setenv("RADAGENT_API_KEY", "stream-test")
        monkeypatch.setenv("RADAGENT_ENABLE_MODEL_STREAMING", "1")

        class FakeStreamResponse:
            def raise_for_status(self) -> None:
                return None

            async def aiter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"first line\\n"}}]}'
                active = json.loads(
                    (tmp_path / "jobs" / "stream_job" / "logs" / "active_model_call.json").read_text()
                )
                transcript = json.loads(
                    (tmp_path / "jobs" / "stream_job" / active["transcript_path"]).read_text()
                )
                assert transcript["status"] == "running"
                assert transcript["progress"]["content"] == "first line\n"
                assert transcript["progress"]["chunk_count"] == 1
                yield 'data: {"choices":[{"delta":{"content":"second line"}}],"usage":{"total_tokens":7}}'
                yield "data: [DONE]"

        class FakeStreamContext:
            async def __aenter__(self):
                return FakeStreamResponse()

            async def __aexit__(self, exc_type, exc, tb):
                return None

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def stream(self, method, url, headers, json):
                assert method == "POST"
                assert json["stream"] is True
                return FakeStreamContext()

            async def aclose(self):
                return None

        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        gw = get_model_gateway()

        result = await gw.call(
            task=ModelTask.CODEGEN,
            system_prompt="system",
            user_prompt="user",
            metadata={"job_id": "stream_job", "module_name": "runtime_app"},
        )

        assert result.error is None
        assert result.content == "first line\nsecond line"
        active = json.loads((tmp_path / "jobs" / "stream_job" / "logs" / "active_model_call.json").read_text())
        final_transcript = json.loads(
            (tmp_path / "jobs" / "stream_job" / active["transcript_path"]).read_text()
        )
        assert final_transcript["progress"]["content"] == "first line\nsecond line"
        assert final_transcript["result"]["content"] == "first line\nsecond line"

    @pytest.mark.asyncio
    async def test_tool_call_transcript_has_waiting_progress_before_provider_returns(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tool-call waits should still show a live status instead of a blank panel."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        gw = get_model_gateway()

        async def fake_tools_call(_profile, req, **_kwargs):
            active = json.loads(
                (tmp_path / "jobs" / "tool_job" / "logs" / "active_model_call.json").read_text()
            )
            transcript = json.loads(
                (tmp_path / "jobs" / "tool_job" / active["transcript_path"]).read_text()
            )
            assert transcript["status"] == "running"
            assert transcript["progress"]["content"]
            assert "等待模型" in transcript["progress"]["content"]
            assert transcript["progress"]["chunk_count"] == 0
            return {
                "content": "",
                "usage": {"total_tokens": 9},
                "reasoning_content": "",
                "tool_calls": [{"id": "c1", "name": "read_file", "arguments": "{}"}],
                "finish_reason": "tool_calls",
            }

        with patch("agent_core.models.client.call_openai_compatible_tools", fake_tools_call):
            result = await gw.call(
                task=ModelTask.CODEGEN,
                system_prompt="system",
                user_prompt="user",
                tools=[{"type": "function", "function": {"name": "read_file"}}],
                metadata={"job_id": "tool_job", "module_name": "agentic_repair"},
            )

        assert result.error is None
        assert result.tool_calls == [{"id": "c1", "name": "read_file", "arguments": "{}"}]

    @pytest.mark.asyncio
    async def test_call_without_job_id_writes_workspace_transcript(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-job calls, such as simulation briefing, still need an accident log."""
        monkeypatch.setenv("RADAGENT_WORKSPACE_ROOT", str(tmp_path))
        gw = get_model_gateway()

        with patch(
            "agent_core.models.gateway.call_openai_compatible_model",
            new_callable=AsyncMock,
            return_value=("not json", {"prompt_tokens": 3}),
        ):
            result = await gw.call(
                task=ModelTask.SIMULATION_BRIEFING,
                system_prompt="system",
                user_prompt="user",
                response_format="json",
                metadata={"module_name": "simulation_briefing"},
            )

        assert result.error is None
        active = json.loads((tmp_path / "logs" / "active_model_call.json").read_text())
        transcript_path = tmp_path / active["transcript_path"]
        transcript = json.loads(transcript_path.read_text())

        assert transcript["job_id"] == ""
        assert transcript["status"] == "passed"
        assert transcript["result"]["content"] == "not json"
        assert transcript["result"]["parsed_json"] is None
        assert "simulation_briefing" in transcript_path.name

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

        content, usage, reasoning_content = await call_openai_compatible_model(
            profile,
            request,
        )

        assert content == '{"ok": true}'
        assert captured_headers[0]["api-key"] == "tp-test"
        assert "Authorization" not in captured_headers[0]
        assert "max_tokens" not in captured_payloads[0]
        assert captured_payloads[0]["max_completion_tokens"] == profile.max_tokens
        assert "temperature" not in captured_payloads[0]
        assert "reasoning_effort" not in captured_payloads[0]
        assert captured_payloads[0]["thinking"] == {"type": "enabled"}
        assert usage.get("reasoning_content") is None
        assert reasoning_content == "checked build errors and interfaces"

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

        content, _usage, reasoning_content = await call_openai_compatible_model(
            profile,
            request,
        )

        assert content == "ok"
        assert reasoning_content == ""
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

    @pytest.mark.asyncio
    async def test_openai_compatible_calls_reuse_http_client_per_profile(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Repeated calls to the same endpoint should reuse the AsyncClient pool."""
        created_clients = []

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                created_clients.append(self)

            async def post(self, url, headers, json):
                return FakeResponse()

            async def aclose(self):
                return None

        monkeypatch.setenv("RADAGENT_API_KEY", "tp-test")
        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        profile = ModelProfile(
            tier=ModelTier.PRO,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="mimo-v2.5-pro",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            api_key_env="RADAGENT_API_KEY",
        )
        request = ModelCallRequest(
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            system_prompt="system",
            user_prompt="user",
        )

        assert (await call_openai_compatible_model(profile, request))[0] == "ok"
        assert (await call_openai_compatible_model(profile, request))[0] == "ok"

        assert len(created_clients) == 1
        assert created_clients[0].kwargs["trust_env"] is False
        assert created_clients[0].kwargs["limits"].max_keepalive_connections == 20
        assert created_clients[0].kwargs["limits"].max_connections == 40

    @pytest.mark.asyncio
    async def test_openai_compatible_retry_uses_retry_after_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Transient 429/5xx errors should back off before retrying."""
        import httpx

        sleeps: list[float] = []
        attempts = 0

        class FakeResponse:
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code
                self.headers = {"Retry-After": "0.25"} if status_code == 429 else {}
                self.request = httpx.Request("POST", "https://models.example/v1/chat/completions")

            def raise_for_status(self) -> None:
                if self.status_code >= 400:
                    raise httpx.HTTPStatusError(
                        f"{self.status_code} error",
                        request=self.request,
                        response=httpx.Response(
                            self.status_code,
                            headers=self.headers,
                            request=self.request,
                        ),
                    )

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def post(self, url, headers, json):
                nonlocal attempts
                attempts += 1
                return FakeResponse(429 if attempts == 1 else 200)

            async def aclose(self):
                return None

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setenv("RADAGENT_API_KEY", "test")
        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        monkeypatch.setattr("agent_core.models.client.asyncio.sleep", fake_sleep)
        profile = ModelProfile(
            tier=ModelTier.PRO,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="compatible-model",
            base_url="https://models.example/v1",
            api_key_env="RADAGENT_API_KEY",
            max_retries=2,
        )
        request = ModelCallRequest(
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            system_prompt="system",
            user_prompt="user",
        )

        content, _usage, _reasoning = await call_openai_compatible_model(profile, request)

        assert content == "ok"
        assert attempts == 2
        assert sleeps == [0.25]

    @pytest.mark.asyncio
    async def test_openai_compatible_retry_does_not_repeat_unauthorized(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Permanent client errors should fail fast instead of burning retries."""
        import httpx

        attempts = 0
        sleeps: list[float] = []

        class FakeResponse:
            headers: dict[str, str] = {}

            def __init__(self) -> None:
                self.request = httpx.Request("POST", "https://models.example/v1/chat/completions")

            def raise_for_status(self) -> None:
                raise httpx.HTTPStatusError(
                    "401 unauthorized",
                    request=self.request,
                    response=httpx.Response(401, request=self.request),
                )

            def json(self):
                raise AssertionError("401 response should not be parsed")

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def post(self, url, headers, json):
                nonlocal attempts
                attempts += 1
                return FakeResponse()

            async def aclose(self):
                return None

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setenv("RADAGENT_API_KEY", "test")
        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        monkeypatch.setattr("agent_core.models.client.asyncio.sleep", fake_sleep)
        profile = ModelProfile(
            tier=ModelTier.PRO,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="compatible-model",
            base_url="https://models.example/v1",
            api_key_env="RADAGENT_API_KEY",
            max_retries=3,
        )
        request = ModelCallRequest(
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            system_prompt="system",
            user_prompt="user",
        )

        with pytest.raises(RuntimeError, match="401 unauthorized"):
            await call_openai_compatible_model(profile, request)

        assert attempts == 1
        assert sleeps == []

    @pytest.mark.asyncio
    async def test_openai_compatible_stream_falls_back_to_non_streaming(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Streaming should not make an otherwise valid provider call fail."""
        import httpx

        post_attempts = 0

        class FakeStreamResponse:
            def __init__(self) -> None:
                self.request = httpx.Request("POST", "https://models.example/v1/chat/completions")

            def raise_for_status(self) -> None:
                raise httpx.HTTPStatusError(
                    "400 stream unsupported",
                    request=self.request,
                    response=httpx.Response(400, request=self.request),
                )

            async def aiter_lines(self):
                raise AssertionError("stream body should not be read after 400")

        class FakeStreamContext:
            async def __aenter__(self):
                return FakeStreamResponse()

            async def __aexit__(self, exc_type, exc, tb):
                return None

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {"choices": [{"message": {"content": "ok fallback"}}], "usage": {}}

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def stream(self, method, url, headers, json):
                return FakeStreamContext()

            async def post(self, url, headers, json):
                nonlocal post_attempts
                post_attempts += 1
                assert "stream" not in json
                return FakeResponse()

            async def aclose(self):
                return None

        chunks: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks.append(chunk)

        monkeypatch.setenv("RADAGENT_API_KEY", "test")
        monkeypatch.setenv("RADAGENT_ENABLE_MODEL_STREAMING", "1")
        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        profile = ModelProfile(
            tier=ModelTier.PRO,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="compatible-model",
            base_url="https://models.example/v1",
            api_key_env="RADAGENT_API_KEY",
            max_retries=0,
        )
        request = ModelCallRequest(
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            system_prompt="system",
            user_prompt="user",
        )

        content, _usage, _reasoning = await call_openai_compatible_model(
            profile,
            request,
            on_chunk=on_chunk,
        )

        assert content == "ok fallback"
        assert post_attempts == 1
        assert chunks == []

    @pytest.mark.asyncio
    async def test_openai_compatible_tools_streams_tool_call_progress(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Native tool calls should stream progress instead of waiting for final POST."""

        class FakeStreamResponse:
            def raise_for_status(self) -> None:
                return None

            async def aiter_lines(self):
                yield (
                    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1",'
                    '"function":{"name":"read_file","arguments":"{\\"path\\": "}}]}}]}'
                )
                yield (
                    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
                    '"function":{"arguments":"\\"src/main.cc\\"}"}}]},"finish_reason":"tool_calls"}],'
                    '"usage":{"total_tokens":11}}'
                )
                yield "data: [DONE]"

        class FakeStreamContext:
            async def __aenter__(self):
                return FakeStreamResponse()

            async def __aexit__(self, exc_type, exc, tb):
                return None

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def stream(self, method, url, headers, json):
                assert method == "POST"
                assert json["stream"] is True
                assert json["tool_choice"] == "auto"
                return FakeStreamContext()

            async def aclose(self):
                return None

        chunks: list[str] = []

        async def on_chunk(chunk: str) -> None:
            chunks.append(chunk)

        monkeypatch.setenv("RADAGENT_API_KEY", "test")
        monkeypatch.setenv("RADAGENT_ENABLE_MODEL_STREAMING", "1")
        monkeypatch.setattr("agent_core.models.client.httpx.AsyncClient", FakeClient)
        profile = ModelProfile(
            tier=ModelTier.PRO,
            provider=ModelProvider.OPENAI_COMPATIBLE,
            model_name="compatible-model",
            base_url="https://models.example/v1",
            api_key_env="RADAGENT_API_KEY",
            max_retries=0,
        )
        request = ModelCallRequest(
            task=ModelTask.CODEGEN,
            tier=ModelTier.PRO,
            system_prompt="system",
            user_prompt="user",
            tools=[{"type": "function", "function": {"name": "read_file"}}],
        )

        result = await call_openai_compatible_tools(profile, request, on_chunk=on_chunk)

        assert chunks == ['准备调用工具 read_file {"path": ', '"src/main.cc"}']
        assert result["finish_reason"] == "tool_calls"
        assert result["usage"] == {"total_tokens": 11}
        assert result["tool_calls"] == [
            {"id": "call_1", "name": "read_file", "arguments": '{"path": "src/main.cc"}'}
        ]
